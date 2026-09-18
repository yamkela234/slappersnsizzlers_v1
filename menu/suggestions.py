from django.db.models import Prefetch

from .models import MenuItem, Option


def suggestions_for(items, limit=3):
    """Available items from categories not already in `items`, cheapest first."""
    taken_categories = {item.category_id for item in items}
    taken_ids = {item.id for item in items}
    return (
        MenuItem.objects.filter(is_available=True)
        .exclude(category_id__in=taken_categories)
        .exclude(id__in=taken_ids)
        .select_related("category")
        .prefetch_related("option_groups", Prefetch("option_groups__options", queryset=Option.objects.filter(is_available=True)))
        .order_by("price")[:limit]
    )
