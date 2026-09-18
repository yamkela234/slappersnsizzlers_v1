from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from home.models import TruckLocation
from menu.models import MenuItem
from menu.suggestions import suggestions_for

from . import utils


def index(request):
    """The cart page."""
    rows, grand_total = utils.cart_summary(request)
    return render(request, "cart/index.html", {
        "rows": rows,
        "grand_total": grand_total,
        "suggestions": suggestions_for([row["item"] for row in rows]) if rows else [],
    })


def _safe_next(request, fallback):
    """Use ?next= only if it points at this host."""
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return candidate
    return fallback


def _parse_qty(raw, default=1):
    try:
        qty = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(qty, utils.MAX_QTY))


def _chosen_options(request, item):
    """Validate the posted option ids against the item's groups. Returns (ids, error)."""
    option_ids = []
    for group in item.option_groups.prefetch_related("options"):
        posted = [v for v in request.POST.getlist(f"group-{group.id}") if v.isdigit()]
        valid = {o.id for o in group.options.all() if o.is_available}
        picked = [int(v) for v in posted if int(v) in valid]
        if group.required and not picked:
            return None, f"Pick a {group.name.lower().replace('choose ', '')} first."
        if len(picked) > group.max_choices:
            return None, f"{group.name}: choose up to {group.max_choices}."
        option_ids.extend(picked)
    return option_ids, None


@require_POST
def add(request, item_id):
    """Add an item (with options and note) to the cart, then redirect."""
    item = get_object_or_404(MenuItem, pk=item_id, is_available=True)
    back_to_item = _safe_next(request, item.get_absolute_url())
    if not TruckLocation.current().is_trading:
        messages.warning(request, "The grill is off right now — you can browse, but not order yet.")
        return redirect(back_to_item)
    qty = _parse_qty(request.POST.get("quantity", 1))
    option_ids, error = _chosen_options(request, item)
    if error:
        messages.error(request, error)
        return redirect(item)
    note = request.POST.get("note", "")
    utils.add_item(request, item.id, qty, option_ids=option_ids, note=note)
    chosen = utils.options_label([o for g in item.option_groups.all() for o in g.options.all() if o.id in option_ids])
    messages.success(request, f"Added {qty} × {item.name}" + (f" ({chosen})" if chosen else ""))
    return redirect(back_to_item)


@require_POST
def update(request, line_key):
    """Set a line's quantity from the cart steppers."""
    try:
        qty = int(request.POST.get("qty", 1))
    except (TypeError, ValueError):
        qty = 1
    utils.set_quantity(request, line_key, min(qty, utils.MAX_QTY))
    return redirect("cart.index")


@require_POST
def remove(request, line_key):
    """Remove one line from the cart."""
    utils.remove_item(request, line_key)
    messages.success(request, "Item removed from your order.")
    return redirect("cart.index")


@require_POST
def clear(request):
    """Wipe the whole cart in one click."""
    utils.clear_cart(request)
    messages.success(request, "Your order was cleared.")
    return redirect("cart.index")
