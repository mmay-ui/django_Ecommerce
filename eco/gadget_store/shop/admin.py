from django.contrib import admin
# shop/admin.py
from django.contrib import admin
from .models import Product, Category, CarouselSlide, Order, OrderItem

admin.site.register(Product)
admin.site.register(Category)
admin.site.register(CarouselSlide)
admin.site.register(Order) 
admin.site.register(OrderItem) 
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'stock_quantity', 'is_available')
    list_filter = ('stock_quantity',)
    search_fields = ('name', 'description')

