# shop/models.py
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone # Import timezone
import random
import string

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.IntegerField(default=0)
    image = models.ImageField(upload_to='product_images/', blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def is_available(self):
        return self.stock_quantity > 0

class CarouselSlide(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='carousel_slides/')
    button_text = models.CharField(max_length=50, blank=True)
    button_url = models.URLField(blank=True)
    order = models.IntegerField(default=0, help_text="Order in which slides appear (lower number first)")
    is_active = models.BooleanField(default=True, help_text="Display this slide on the homepage carousel")

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.title # <-- NILAGYAN KO NA NG TAMANG SPELLING DITO

# --- BAGONG MODEL: VOUCHER ---
class Voucher(models.Model):
    code = models.CharField(max_length=20, unique=True, blank=True)
    description = models.CharField(max_length=255)
    discount_type = models.CharField(max_length=10, choices=[('percentage', 'Percentage'), ('fixed', 'Fixed Amount')], default='percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    minimum_purchase = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.code} ({self.discount_value}% off)"

    def is_valid(self):
        now = timezone.now()
        return self.is_active and self.valid_from <= now <= self.valid_until

    def generate_code(self, length=8):
        characters = string.ascii_uppercase + string.digits
        code = ''.join(random.choice(characters) for i in range(length))
        while Voucher.objects.filter(code=code).exists():
            code = ''.join(random.choice(characters) for i in range(length))
        return code

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self.generate_code()
        super().save(*args, **kwargs)

# --- ORDER MODEL ---
class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Payment'),
        ('paid', 'Paid'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]
    
    customer_name = models.CharField(max_length=200, blank=True, null=True)
    customer_email = models.EmailField(blank=True, null=True)
    customer_phone = models.CharField(max_length=20, blank=True, null=True)
    customer_username = models.CharField(max_length=150, blank=True, null=True)

    shipping_address_line1 = models.CharField(max_length=255, blank=True, null=True)
    shipping_address_line2 = models.CharField(max_length=255, blank=True, null=True)
    shipping_city = models.CharField(max_length=100, blank=True, null=True)
    shipping_postal_code = models.CharField(max_length=20, blank=True, null=True)
    shipping_country = models.CharField(max_length=100, blank=True, null=True)

    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    final_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    
    # Link sa Voucher
    used_voucher = models.ForeignKey(Voucher, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders_used')

    def __str__(self):
        display_name = self.customer_email or self.customer_username or self.customer_name or "Guest"
        return f"Order #{self.id} - {display_name}"

    def save(self, *args, **kwargs):
        if self.total_amount is not None and self.discount_amount is not None:
            self.final_amount = self.total_amount - self.discount_amount
        super().save(*args, **kwargs)

# shop/models.py
# ... (other models) ...

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    quantity = models.PositiveIntegerField()
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        # CHECK KUNG MAY PRODUCT BAGO GAMITIN YUNG .name
        if self.product:
            return f"{self.quantity} x {self.product.name} in Order #{self.order.id}"
        else:
            # Kung wala, magpakita ng placeholder para hindi mag-error
            return f"{self.quantity} x Unknown Product in Order #{self.order.id}"

    def subtotal(self):
        return self.quantity * self.price_at_purchase