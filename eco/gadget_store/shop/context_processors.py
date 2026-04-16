# shop/context_processors.py
from .cart import Cart # Import your Cart class

def cart(request):
    """Makes the cart object available in the context of all templates."""
    return {'cart': Cart(request)}