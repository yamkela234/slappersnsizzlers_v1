from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from cart import utils as cart_utils
from home.models import TruckLocation

from .forms import CheckoutForm
from .models import Order, OrderItem, PickupSlot

ORDER_IDS_SESSION_KEY = "order_ids"


def _session_order_ids(request):
    return [i for i in request.session.get(ORDER_IDS_SESSION_KEY, []) if isinstance(i, int)]


def index(request):
    """Order history: the user's orders, or the ones placed from this session."""
    if request.user.is_authenticated:
        orders = request.user.orders.prefetch_related("items").select_related("slot")
    else:
        orders = Order.objects.filter(id__in=_session_order_ids(request)).prefetch_related("items").select_related("slot")
    return render(request, "orders/index.html", {"orders": orders})


def checkout(request):
    """GET: slot picker + summary + contact form. POST: turn the cart into an Order."""
    truck = TruckLocation.current()
    rows, goods_total = cart_utils.cart_summary(request)
    if not rows:
        messages.warning(request, "Your order is empty — add something tasty first.")
        return redirect("home.index")
    if not truck.is_trading:
        return render(request, "orders/checkout.html", {"truck": truck, "closed": True, "rows": rows, "goods_total": goods_total})
    slots = PickupSlot.upcoming(truck)
    if request.method == "POST":
        form = CheckoutForm(request.POST)
        chosen_slot, slot_error = _chosen_slot(request, slots)
        if form.is_valid() and not slot_error:
            tip = form.tip_amount()
            try:
                with transaction.atomic():
                    if chosen_slot is not None:
                        locked = PickupSlot.objects.select_for_update().get(pk=chosen_slot.pk)
                        if locked.taken >= locked.capacity:
                            raise _SlotFull()
                        PickupSlot.objects.filter(pk=locked.pk).update(taken=F("taken") + 1)
                    order = Order.objects.create(
                        user=request.user if request.user.is_authenticated else None,
                        customer_name=form.cleaned_data["customer_name"],
                        phone=form.cleaned_data["phone"],
                        slot=chosen_slot,
                        tip=tip,
                        total=goods_total + tip,
                    )
                    OrderItem.objects.bulk_create([
                        OrderItem(
                            order=order,
                            menu_item=row["item"],
                            name_snapshot=row["item"].name,
                            price_snapshot=row["unit_price"],
                            quantity=row["quantity"],
                            options_snapshot=cart_utils.options_label(row["options"]),
                            note=row["note"],
                        )
                        for row in rows
                    ])
            except _SlotFull:
                messages.error(request, "That window just filled up — pick another.")
                return redirect("orders.checkout")
            cart_utils.clear_cart(request)
            ids = _session_order_ids(request)
            ids.append(order.id)
            request.session[ORDER_IDS_SESSION_KEY] = ids
            messages.success(request, f"Order #{order.id} placed! We're on it.")
            return redirect("orders.confirmation", order_id=order.id)
        if slot_error:
            messages.error(request, slot_error)
    else:
        form = CheckoutForm()
    return render(request, "orders/checkout.html", {
        "truck": truck,
        "form": form,
        "rows": rows,
        "goods_total": goods_total,
        "slots": slots,
        "selected_slot": request.POST.get("slot", "asap"),
    })


class _SlotFull(Exception):
    """Raised inside the checkout transaction to roll it back when the chosen
    window filled between page load and submit."""


def _chosen_slot(request, slots):
    """"asap" → (None, None); a slot id → (that slot, None) if it's one we
    offered; anything else → (None, error)."""
    raw = request.POST.get("slot", "asap")
    if raw == "asap":
        return None, None
    for slot in slots:
        if str(slot.pk) == raw:
            return slot, None
    return None, "That collection window isn't available — pick another."


def _visible_to(request, order):
    """Owner, staff, or the session that placed the order."""
    if request.user.is_authenticated and order.user_id == request.user.id:
        return True
    if request.user.is_staff:
        return True
    return order.id in _session_order_ids(request)


def show(request, order_id):
    """Order status page."""
    order = get_object_or_404(Order.objects.select_related("slot"), pk=order_id)
    if not _visible_to(request, order):
        raise PermissionDenied
    return render(request, "orders/show.html", {
        "order": order,
        "items": order.items.select_related("menu_item"),
        "steps": _steps(order),
        "truck": TruckLocation.current(),
    })


def _steps(order):
    """The four-step rail with each step's state."""
    current = Order.FLOW.index(order.status) if order.status in Order.FLOW else -1
    labels = dict(Order.Status.choices)
    return [
        {"key": key, "label": labels[key], "state": "past" if i < current else "now" if i == current else "future"}
        for i, key in enumerate(Order.FLOW)
    ]


def status_json(request, order_id):
    """Current status as JSON, polled by the status page."""
    order = get_object_or_404(Order, pk=order_id)
    if not _visible_to(request, order):
        raise PermissionDenied
    return JsonResponse({"status": order.status})


def confirmation(request, order_id):
    """Post-checkout confirmation with the collection code."""
    order = get_object_or_404(Order.objects.select_related("slot"), pk=order_id)
    if not _visible_to(request, order):
        raise PermissionDenied
    return render(request, "orders/confirmation.html", {
        "order": order,
        "items": order.items.select_related("menu_item"),
        "truck": TruckLocation.current(),
    })
