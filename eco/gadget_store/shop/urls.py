# shop/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.homepage, name='homepage'), # Route for the homepage
    path('products/', views.product_list, name='product_list'), # Route for all products
    # New path for category filtering
    path('category/<str:category_slug>/', views.category_product_list, name='category_product_list'), 
    path('product/<int:product_id>/', views.product_detail, name='product_detail'),
    path('cart/add/<int:product_id>/', views.cart_add, name='cart_add'),
    path('cart/update/<int:product_id>/', views.cart_update, name='cart_update'),
    path('cart/remove/<int:product_id>/', views.cart_remove, name='cart_remove'),
    path('cart/', views.cart_detail, name='cart_detail'),
    path('checkout/', views.checkout_view, name='checkout'), 
    path('checkout/success/<int:order_id>/', views.order_success_view, name='order_success'),
     path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'), # Optional, but recommended
    path('profile/', views.profile_view, name='profile'), # For the profile icon link
    path('accounts/profile/', views.profile_view, name='profile'), # Siguraduhing ito ay tama
    path('accounts/profile/orders/', views.order_history_view, name='order_history'), # Ito ang bagong URL
    # ... iba pa ...
]