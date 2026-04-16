# shop/cart.py

from django.conf import settings
from .models import Product # Assuming Product model is in the same app

class Cart:
    def __init__(self, request):
        self.session = request.session
        cart = self.session.get('cart')
        if not cart:
            # Create an empty cart if it doesn't exist
            cart = self.session['cart'] = {}
        self.cart = cart

    def add(self, product, quantity=1, override_quantity=False):
        product_id = str(product.id)
        if product_id not in self.cart:
            self.cart[product_id] = {'quantity': 0}
        
        if override_quantity:
            self.cart[product_id]['quantity'] = quantity
        else:
            self.cart[product_id]['quantity'] += quantity
        self.save()

    def remove(self, product):
        product_id = str(product.id)
        if product_id in self.cart:
            del self.cart[product_id]
            self.save()

    # === IDADAGDAG MO ITO ===
    def update(self, product, quantity):
        if quantity > 0:
            # Update the quantity if it's greater than 0
            self.cart[str(product.id)] = {'quantity': quantity}
            self.save()
        else:
            # If quantity is 0 or less, remove the item
            self.remove(product)
    # =========================

    def save(self):
        self.session.modified = True

    def __len__(self):
        # Return the total number of items in the cart
        return sum(item['quantity'] for item in self.cart.values())

    def __iter__(self):
        # Iterate over items in the cart and yield product information
        product_ids = self.cart.keys()
        products = Product.objects.filter(id__in=product_ids)
        
        cart = self.cart.copy()
        for product in products:
            cart[str(product.id)]['product'] = product
        
        for item in cart.values():
            yield item

    def get_total_price(self):
        # Calculate the total price of all items in the cart
        return sum(item['product'].price * item['quantity'] for item in self.cart.values() if 'product' in item)

    def clear(self):
        # Remove cart from session
        del self.session['cart']
        self.session.modified = True