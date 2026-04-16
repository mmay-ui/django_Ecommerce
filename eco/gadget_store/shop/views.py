# shop/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.conf import settings
from .models import Product, Category, CarouselSlide, Order, OrderItem, Voucher # Import Voucher model
from .cart import Cart
from django.contrib import messages
from django.core.mail import send_mail, BadHeaderError
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging
from django.contrib.auth import login, authenticate, logout
from .forms import CustomUserCreationForm, CustomAuthenticationForm
from django.contrib.auth.decorators import login_required
from django.utils import timezone # Import timezone
from decimal import Decimal # Import Decimal


logger = logging.getLogger(__name__)

# --- Helper to get or initialize cart ---
def get_cart(request):
    if 'cart' not in request.session:
        request.session['cart'] = {}
    return Cart(request)

# --- Login View ---
def login_view(request):
    if request.method == 'POST':
        form = CustomAuthenticationForm(request, data=request.POST) 
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password) 
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {username}!")
                redirect_url = request.GET.get('next', 'homepage')
                return redirect(redirect_url)
            else:
                messages.error(request, "Invalid username or password.")
        else:
             messages.error(request, "Invalid username or password.")
    else:
        form = CustomAuthenticationForm(request) 
    
    if request.user.is_authenticated:
        return redirect('homepage')
        
    return render(request, 'registration/login.html', {'form': form})

# --- Signup View ---
def signup_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST) 
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created successfully! You are now logged in.")
            return redirect('homepage')
        else:
            messages.error(request, "Account creation failed. Please check the errors below.")
    else:
        form = CustomUserCreationForm() 
        
    if request.user.is_authenticated:
        return redirect('homepage')
        
    return render(request, 'registration/signup.html', {'form': form})

# --- Logout View ---
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('login')

# --- Profile View ---
@login_required
def profile_view(request):
    return render(request, 'registration/profile.html', {'user': request.user})

# --- Order History View ---
@login_required
def order_history_view(request):
    user_orders = Order.objects.filter(customer_email=request.user.email).order_by('-created_at')
    
    orders_to_pay = user_orders.filter(status='pending')
    orders_to_ship = user_orders.filter(status='processing')
    orders_to_receive = user_orders.filter(status='shipped')
    orders_to_rate = user_orders.filter(status='delivered')

    # --- Fetch available vouchers ---
    available_vouchers = Voucher.objects.filter(
        is_active=True,
        valid_from__lte=timezone.now(),
        valid_until__gte=timezone.now()
    )
    voucher_count = available_vouchers.count()
    # --- End fetch available vouchers ---

    return render(request, 'registration/order_history.html', {
        'orders_to_pay': orders_to_pay,
        'orders_to_ship': orders_to_ship,
        'orders_to_receive': orders_to_receive,
        'orders_to_rate': orders_to_rate,
        'available_vouchers': available_vouchers, # Pass vouchers to template
        'voucher_count': voucher_count,          # Pass voucher count to template
    })

# --- Homepage View ---
@login_required
def homepage(request):
    products = Product.objects.filter(stock_quantity__gt=0).order_by('-created_at')
    cart = get_cart(request)
    carousel_slides = CarouselSlide.objects.filter(is_active=True).order_by('order')
    return render(request, 'shop/homepage.html', {
        'products': products,
        'cart': cart,
        'carousel_slides': carousel_slides
    })

# --- Cart Detail View ---
@login_required
def cart_detail(request):
    cart = get_cart(request)
    cart_items_display = []
    total_price = 0
    all_items_valid = True

    for item_id, item_data in list(cart.cart.items()):
        try:
            product = Product.objects.get(id=item_id)
            quantity = item_data['quantity']
            item_subtotal = product.price * quantity

            if not product.is_available() or product.stock_quantity < quantity:
                all_items_valid = False
                available_stock = product.stock_quantity
                if available_stock == 0:
                    messages.error(request, f"'{product.name}' is now out of stock and has been removed from your cart.")
                    cart.remove(product)
                    continue
                else:
                    new_quantity = min(quantity, available_stock)
                    messages.warning(request, f"'{product.name}' quantity adjusted to {new_quantity} due to limited stock.")
                    cart.update(product, new_quantity)
                    item_subtotal = product.price * new_quantity
                    quantity = new_quantity

            cart_items_display.append({
                'product': product,
                'quantity': quantity,
                'price': product.price,
                'subtotal': item_subtotal,
                'id': item_id
            })
            total_price += item_subtotal

        except Product.DoesNotExist:
            messages.error(request, f"A product in your cart (ID: {item_id}) does not exist anymore and has been removed.")
            cart.remove(Product(id=item_id))
            continue

    return render(request, 'shop/cart.html', {
        'cart': cart,
        'cart_items': cart_items_display,
        'total_price': total_price,
        'all_items_valid': all_items_valid,
    })

# --- Checkout View ---
@login_required
def checkout_view(request):
    cart = get_cart(request)
    cart_items_for_checkout = []
    subtotal = Decimal('0.00') # Initialize as Decimal
    applied_voucher = None
    discount_amount = Decimal('0.00') # Initialize as Decimal
    final_amount = Decimal('0.00')   # Initialize as Decimal
    voucher_code_submitted = ""
    voucher_error = None # Initialize voucher_error to None

    # --- Check if a voucher is applied from POST data ---
    if request.method == 'POST':
        voucher_code_submitted = request.POST.get('voucher_code', '').strip()
        if voucher_code_submitted:
            try:
                now = timezone.now()
                # Fetch voucher and check validity
                voucher = Voucher.objects.get(code__iexact=voucher_code_submitted, is_active=True, valid_from__lte=now, valid_until__gte=now)
                
                if voucher.is_valid():
                    # Check minimum purchase requirement
                    if voucher.minimum_purchase <= cart.get_total_price(): # Assuming cart has get_total_price() method
                        applied_voucher = voucher
                        if voucher.discount_type == 'percentage':
                            # Ensure calculation is done with Decimal
                            discount_amount = (Decimal(str(cart.get_total_price())) * Decimal(str(voucher.discount_value))) / Decimal('100')
                        else: # fixed amount
                            discount_amount = voucher.discount_value
                        
                        # Ensure discount doesn't exceed total amount and is Decimal
                        discount_amount = min(Decimal(str(discount_amount)), subtotal)
                        messages.success(request, f"Voucher '{voucher.code}' applied! Discount: ₱{discount_amount:.2f}")
                    else:
                        voucher_error = f"Voucher '{voucher.code}' requires a minimum purchase of ₱{voucher.minimum_purchase:.2f}."
                else:
                    voucher_error = f"Voucher '{voucher.code}' is expired or inactive."
            except Voucher.DoesNotExist:
                voucher_error = f"Voucher code '{voucher_code_submitted}' not found."
            except Exception as e: # Catch any other exception during voucher processing
                logger.error(f"Error applying voucher: {e}")
                voucher_error = "An error occurred while applying the voucher."
            
            # Display voucher error message if any
            if voucher_error:
                messages.error(request, voucher_error)
                # Re-render the checkout page with existing data and error message
                # Important: Reset discount and final amount if voucher application failed
                return render(request, 'shop/checkout.html', {
                    'cart_items': cart_items_for_checkout,
                    'subtotal': subtotal,
                    'discount_amount': Decimal('0.00'), # Reset discount if error
                    'final_amount': subtotal, # Reset final amount if error
                    'applied_voucher': None, # Reset applied voucher if error
                    'payment_methods': ['Cash on Delivery', 'GCash', 'PayMaya', 'Credit Card', 'Bank Transfer'],
                    'customer_name': customer_name,
                    'customer_email': customer_email,
                    'customer_phone': customer_phone,
                    'shipping_address_line1': shipping_address_line1,
                    'shipping_address_line2': shipping_address_line2,
                    'shipping_city': shipping_city,
                    'shipping_postal_code': shipping_postal_code,
                    'shipping_country': shipping_country,
                    'selected_payment_method': payment_method,
                    'voucher_code': voucher_code_submitted, # Keep voucher code in form if submitted
                })

    # --- Recalculate cart items and subtotal ---
    current_cart_total = Decimal('0.00') # Initialize as Decimal
    for item_id, item_data in list(cart.cart.items()):
        try:
            product = Product.objects.get(id=item_id)
            quantity = item_data['quantity']
            # Ensure price is Decimal for calculation
            item_subtotal = product.price * Decimal(str(quantity))
            current_cart_total += item_subtotal

            if not product.is_available() or product.stock_quantity < quantity:
                messages.error(request, f"'{product.name}' is no longer available in the quantity you selected. Please update your cart.")
                available_stock = product.stock_quantity
                if available_stock == 0:
                    cart.remove(product)
                else:
                    cart.update(product, available_stock)
                return redirect('cart_detail')

            cart_items_for_checkout.append({
                'product': product,
                'quantity': quantity,
                'price': product.price,
                'subtotal': item_subtotal,
                'id': item_id
            })
        except Product.DoesNotExist:
            messages.error(request, f"A product in your cart (ID: {item_id}) does not exist anymore and has been removed.")
            cart.remove(Product(id=item_id))
            return redirect('cart_detail')

    subtotal = current_cart_total

    # --- Apply discount if voucher is valid ---
    if applied_voucher:
        # Ensure discount_amount is Decimal before comparison and subtraction
        discount_amount = Decimal(str(discount_amount))
        discount_amount = min(discount_amount, subtotal) # Ensure discount doesn't exceed subtotal
        final_amount = subtotal - discount_amount
    else:
        final_amount = subtotal # subtotal is already Decimal

    # --- Handle POST request for placing the order ---
    if request.method == 'POST':
        customer_name = request.POST.get('customer_name')
        customer_email = request.POST.get('customer_email')
        customer_phone = request.POST.get('customer_phone')
        payment_method = request.POST.get('payment_method')
        
        shipping_address_line1 = request.POST.get('shipping_address_line1')
        shipping_address_line2 = request.POST.get('shipping_address_line2')
        shipping_city = request.POST.get('shipping_city')
        shipping_postal_code = request.POST.get('shipping_postal_code')
        shipping_country = request.POST.get('shipping_country')

        required_fields = [
            customer_name, customer_email, customer_phone, payment_method,
            shipping_address_line1, shipping_city, shipping_postal_code, shipping_country
        ]
        if not all(required_fields):
            messages.error(request, "Please fill in all required fields, including shipping address.")
            return render(request, 'shop/checkout.html', {
                'cart_items': cart_items_for_checkout,
                'subtotal': subtotal,
                'discount_amount': discount_amount, # Pass discount amount
                'final_amount': final_amount,       # Pass final amount
                'applied_voucher': applied_voucher, # Pass applied voucher object
                'payment_methods': ['Cash on Delivery', 'GCash', 'PayMaya', 'Credit Card', 'Bank Transfer'],
                'customer_name': customer_name,
                'customer_email': customer_email,
                'customer_phone': customer_phone,
                'shipping_address_line1': shipping_address_line1,
                'shipping_address_line2': shipping_address_line2,
                'shipping_city': shipping_city,
                'shipping_postal_code': shipping_postal_code,
                'shipping_country': shipping_country,
                'selected_payment_method': payment_method,
                'voucher_code': voucher_code_submitted, # Keep voucher code in form if submitted
            })

        try:
            order = Order.objects.create(
                customer_name=customer_name,
                customer_email=customer_email,
                customer_username=request.user.username,
                customer_phone=customer_phone,
                payment_method=payment_method,
                
                shipping_address_line1=shipping_address_line1,
                shipping_address_line2=shipping_address_line2,
                shipping_city=shipping_city,
                shipping_postal_code=shipping_postal_code,
                shipping_country=shipping_country,
                
                total_amount=subtotal,
                discount_amount=discount_amount, # Save discount amount
                final_amount=final_amount,       # Save final amount
                status='pending',
                used_voucher=applied_voucher     # Save the used voucher object
            )

            for item_data in cart_items_for_checkout:
                OrderItem.objects.create(
                    order=order,
                    product=item_data['product'],
                    quantity=item_data['quantity'],
                    price_at_purchase=item_data['product'].price
                )
                product = item_data['product']
                product.stock_quantity -= item_data['quantity']
                product.save()

            request.session['cart'] = {} # Clear cart
            # Optionally clear applied voucher from session if you were storing it there
            # request.session.pop('applied_voucher_code', None) 

            # --- Handle Payment Method Redirection ---
            if payment_method == 'Cash on Delivery':
                return redirect('order_success', order_id=order.id)
            elif payment_method in ['GCash', 'PayMaya', 'Credit Card']:
                messages.info(request, f"Processing payment via {payment_method}. You will be redirected shortly.")
                # Placeholder redirect: Implement actual payment gateway integration here
                return redirect('order_success', order_id=order.id) 
            elif payment_method == 'Bank Transfer':
                # Placeholder redirect: Implement bank transfer instructions/confirmation page
                return redirect('order_success', order_id=order.id)
            else:
                messages.error(request, "Invalid payment method selected.")
                return redirect('checkout')

        except Exception as e: # This block is now safer
            logger.error(f"Error creating order: {e}")
            print(f"DEBUG ERROR: {e}") # Print the actual error to the console for debugging
            messages.error(request, f"An error occurred while placing your order: {e}. Please try again.")
            return redirect('checkout')


    # --- Render checkout page (GET request or POST with errors) ---
    return render(request, 'shop/checkout.html', {
        'cart_items': cart_items_for_checkout,
        'subtotal': subtotal,
        'discount_amount': discount_amount, # Pass discount amount
        'final_amount': final_amount,       # Pass final amount
        'applied_voucher': applied_voucher, # Pass applied voucher object
        'payment_methods': ['Cash on Delivery', 'GCash', 'PayMaya', 'Credit Card', 'Bank Transfer'],
        'customer_name': request.user.get_full_name() or request.user.username,
        'customer_email': request.user.email,
        'customer_phone': '',
        'shipping_address_line1': '',
        'shipping_address_line2': '',
        'shipping_city': '',
        'shipping_postal_code': '',
        'shipping_country': '',
        'selected_payment_method': '',
        'voucher_code': voucher_code_submitted, # Keep voucher code in form if submitted
    })

# --- Order Success View ---
@login_required
def order_success_view(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    # --- Send Email Receipt ---
    subject = f"Your GadgetHub Order Confirmation - #{order.id}"
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [order.customer_email]

    email_sent_successfully = False
    try:
        # === IMPORTANT CHANGE: Update and Save order BEFORE rendering email ===
        order.status = 'paid'
        # Placeholder transaction ID. Replace with actual from payment gateway.
        order.transaction_id = f"TEST-{order.id}-{order.created_at.strftime('%Y%m%d%H%M%S')}"
        order.save() # Save the changes first
        # =====================================================================

        # Now render the email with the updated order details
        html_message = render_to_string('email/order_receipt.html', {'order': order})
        plain_message = strip_tags(html_message)

        send_mail(subject, plain_message, from_email, recipient_list, html_message=html_message, fail_silently=False)
        
        email_sent_successfully = True
        messages.success(request, "Your order has been placed successfully! A confirmation email has been sent.")

    except BadHeaderError:
        logger.error(f"Bad header found when trying to send email for order #{order.id}.")
        messages.error(request, "Order placed, but there was an issue with the email format. Please check your inbox or contact support.")
        # Status remains 'pending' if email fails due to bad header
    except Exception as e:
        logger.error(f"Failed to send order confirmation email for order #{order.id}: {e}")
        messages.error(request, f"Order placed successfully, but failed to send confirmation email. Please check your inbox or contact support. Error: {e}")
        print(f"DEBUG ERROR: {e}") # Print the actual error to the console for debugging
        # Status remains 'pending' if email fails for other reasons

    # Render the success page regardless of email status
    # The order object passed here will reflect the 'paid' status if email was successful,
    # or 'pending' if email failed.
    return render(request, 'shop/order_success.html', {'order': order})


# --- Product List View ---
@login_required # Added decorator here
def product_list(request):
    products = Product.objects.filter(stock_quantity__gt=0).order_by('name')
    categories = Category.objects.all()
    cart = get_cart(request)
    return render(request, 'shop/product_list.html', {
        'products': products,
        'categories': categories,
        'cart': cart
    })

# --- Category Product List View ---
@login_required # Added decorator here
def category_product_list(request, category_slug):
    try:
        category = Category.objects.get(name__iexact=category_slug.replace('-', ' ').capitalize())
    except Category.DoesNotExist:
        messages.error(request, f"Category '{category_slug}' not found.")
        return redirect('product_list')

    products = Product.objects.filter(category=category, stock_quantity__gt=0).order_by('name')
    categories = Category.objects.all()
    cart = get_cart(request)
    return render(request, 'shop/product_list.html', {
        'category': category,
        'products': products,
        'categories': categories,
        'cart': cart
    })

# --- Product Detail View ---
@login_required # Added decorator here
def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart = get_cart(request)
    is_available = product.is_available()
    return render(request, 'shop/product_detail.html', {
        'product': product,
        'cart': cart,
        'is_available': is_available,
    })

# --- Cart Add View ---
# Note: Cart add might be accessible without login for guest users,
# but checkout definitely needs login. Adjust if needed.
def cart_add(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    if not product.is_available():
        messages.error(request, f"'{product.name}' is currently out of stock.")
        return redirect('product_detail', product_id=product_id)

    cart = get_cart(request)
    cart.add(product=product, quantity=1)
    messages.success(request, f"'{product.name}' added to cart.")
    return redirect('cart_detail')

# --- Cart Update View ---
# Note: Cart update might be accessible without login for guest users.
def cart_update(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    try:
        quantity = int(request.POST.get('quantity', 0))
    except ValueError:
        messages.error(request, "Invalid quantity entered.")
        return redirect('cart_detail')

    cart = get_cart(request)

    if quantity <= 0:
        cart.remove(product)
        messages.info(request, f"'{product.name}' removed from cart.")
    elif not product.is_available() or product.stock_quantity < quantity:
        messages.error(request, f"Not enough stock for '{product.name}'. Available: {product.stock_quantity}.")
    else:
        cart.update(product, quantity)
        messages.success(request, f"'{product.name}' quantity updated in cart.")

    return redirect('cart_detail')

# --- Cart Remove View ---
@login_required # Added decorator here
def cart_remove(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart = get_cart(request)
    cart.remove(product)
    messages.info(request, f"'{product.name}' removed from cart.")
    return redirect('cart_detail')

# --- Placeholder for CarouselSlide model if not defined elsewhere ---
# class CarouselSlide(models.Model):
#     title = models.CharField(max_length=200)
#     description = models.TextField()
#     image = models.ImageField(upload_to='carousel_images/')
#     button_text = models.CharField(max_length=50, blank=True, null=True)
#     button_url = models.URLField(blank=True, null=True)
#     order = models.IntegerField(default=0)
#     is_active = models.BooleanField(default=True)
#
#     def __str__(self):
#         return self.titlet