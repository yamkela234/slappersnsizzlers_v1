from .utils import count_items


def cart_count(request):
    """Total quantity in the cart, for the navbar badge."""
    return {"cart_count": count_items(request)}
