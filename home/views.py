from django.db.models import Prefetch
from django.shortcuts import render

from menu.models import MenuItem, Option


def index(request):
    items = MenuItem.objects.filter(is_available=True).select_related("category").prefetch_related("option_groups", Prefetch("option_groups__options", queryset=Option.objects.filter(is_available=True)))
    return render(request, "home/index.html", {"items": items})
