from .models import Order, OrderItem


def has_collected_item(user, menu_item):
    """True if the user has a collected order containing this item."""
    if not user.is_authenticated:
        return False
    return OrderItem.objects.filter(
        order__user=user,
        order__status=Order.Status.COLLECTED,
        menu_item=menu_item,
    ).exists()
