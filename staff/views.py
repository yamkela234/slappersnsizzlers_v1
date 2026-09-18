from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.models import Group, User
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from home.models import TruckLocation
from menu.models import Category, MenuItem, Option, OptionGroup, Review
from orders.models import SLOT_MINUTES, Order, PickupSlot

from .forms import InviteForm, MenuItemForm, TruckForm
from .permissions import MANAGER_GROUPS, is_manager, manager_required, role_of, staff_member_required

LIVE = (Order.Status.PENDING, Order.Status.PREPARING, Order.Status.READY)
NEXT_LABELS = {"pending": "Start cooking", "preparing": "Mark ready", "ready": "Mark collected"}
SLOT_CAPACITY_CEILING = 40

NAV = [
    ("Operations", [
        ("dashboard", "Dashboard", "ri-dashboard-3-line", "staff.dashboard", None, False),
        ("queue", "Live queue", "ri-fire-line", "staff.queue", "live", False),
        ("orders", "Orders", "ri-receipt-line", "staff.orders", None, False),
    ]),
    ("Menu", [
        ("items", "Items", "ri-restaurant-line", "staff.items", None, False),
        ("options", "Options", "ri-list-check-2", "staff.options", None, True),
    ]),
    ("Customers", [
        ("reviews", "Reviews", "ri-star-line", "staff.reviews", "flagged", True),
    ]),
    ("Setup", [
        ("truck", "Truck & hours", "ri-truck-line", "staff.truck", None, True),
        ("slots", "Collection windows", "ri-time-line", "staff.slots", None, True),
        ("staff", "Staff", "ri-team-line", "staff.people", None, True),
    ]),
]

SUBTITLES = {
    "orders": "Every order placed today, guest or signed in.",
    "items": "Five things. Keep it that way.",
    "options": "What a dish asks the customer before it goes in the basket.",
    "reviews": "Hide spam, keep the honest ones.",
    "truck": "The one row that drives the context bar and the checkout guard.",
    "slots": "15-minute windows, capped by what the grill can turn out.",
    "staff": "Who can open the queue and change the menu.",
}
TITLES = {
    "dashboard": "Today at the truck", "orders": "Orders", "items": "Menu items", "options": "Option groups",
    "reviews": "Reviews", "truck": "Truck & trading hours", "slots": "Collection windows", "staff": "Staff",
}


def _live_count():
    return Order.objects.filter(created_at__date=timezone.localdate(), status__in=LIVE).count()


def _flagged_count():
    """Unhidden reviews rated ≤ 2."""
    return Review.objects.filter(is_hidden=False, rating__lte=2).count()


def _shell(request, screen, title=None, sub=None):
    """Everything staff/base.html needs, computed once per render."""
    truck = TruckLocation.current()
    manager = is_manager(request.user)
    live = _live_count()
    flagged = _flagged_count()
    badges = {"live": live, "flagged": flagged}
    nav = [
        {"label": label, "items": [
            {"key": key, "label": text, "icon": icon, "url": reverse(name), "active": key == screen, "badge_key": badge, "badge": badges.get(badge, 0)}
            for key, text, icon, name, badge, managers_only in items
            if manager or not managers_only
        ]}
        for label, items in NAV
    ]
    return {
        "screen": screen,
        "page_title": title or TITLES.get(screen, ""),
        "page_sub": sub or SUBTITLES.get(screen, ""),
        "nav": nav,
        "truck": truck,
        "next_slot": next(iter(PickupSlot.upcoming(truck, limit=1)), None),
        "role": role_of(request.user),
        "show_takings": manager,
        "live_count": live,
        "flagged_count": flagged,
    }


def _is_fetch(request):
    return request.headers.get("X-Requested-With") == "fetch"


def _done(request, message, redirect_to, updates=None, ok=True):
    """Flash + redirect for a browser POST; JSON for staff.js. See the module docstring."""
    if _is_fetch(request):
        return JsonResponse({"ok": ok, "message": message, "updates": updates or {}}, status=200 if ok else 400)
    messages.add_message(request, messages.SUCCESS if ok else messages.ERROR, message)
    return redirect(redirect_to)


def _fragment(request, template, context):
    """Render one partial to a string."""
    return render_to_string(template, context, request=request)


def _safe_next(request, default):
    """Use ?next= only if it points at this host."""
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return nxt
    return default


def _todays_orders():
    return Order.objects.filter(created_at__date=timezone.localdate()).select_related("slot").prefetch_related("items")


def _live_orders():
    """Oldest first: the kitchen works the queue from the top."""
    return [o for o in _todays_orders().order_by("created_at") if o.status in LIVE]


def _todays_slots(truck, now):
    """Today's windows, including full ones."""
    PickupSlot.upcoming(truck, now=now)
    return list(PickupSlot.objects.filter(start__gt=now - timedelta(minutes=SLOT_MINUTES), start__lt=truck.closes_at(now)))


def _attention(sold_out, full_slots, flagged):
    """The Needs-attention rows: one per condition, each with a place to go."""
    notes = [{"kind": "warning", "icon": "ri-error-warning-line", "text": f"{item.name} is off the menu", "action": "Menu", "url": reverse("staff.items")} for item in sold_out]
    notes += [{"kind": "info", "icon": "ri-time-line", "text": f"{slot.label()} is full — hidden from checkout", "action": "Windows", "url": reverse("staff.slots")} for slot in full_slots]
    if flagged:
        notes.append({"kind": "danger", "icon": "ri-star-line", "text": f"{flagged} low-star review{'s' if flagged > 1 else ''} to look at", "action": "Reviews", "url": reverse("staff.reviews")})
    if not notes:
        notes.append({"kind": "success", "icon": "ri-checkbox-circle-fill", "text": "Nothing needs you right now.", "action": "", "url": ""})
    return notes


@staff_member_required
def dashboard(request):
    """Answer "is anything wrong, and what's cooking" in one look."""
    now = timezone.now()
    today = timezone.localdate()
    orders = list(_todays_orders())
    live = [o for o in orders if o.status in LIVE]
    truck = TruckLocation.current()
    takings = sum((o.total for o in orders if o.status != Order.Status.CANCELLED), Decimal("0.00"))
    prep = [o.prep_seconds() for o in orders if o.prep_seconds() is not None]
    avg_prep = round(sum(prep) / len(prep) / 60) if prep else None
    first = min((o.created_at for o in orders), default=None)
    slots = _todays_slots(truck, now)
    sub = f"{today:%A} {today.day} {today:%B}"
    sub += f" · service started {timezone.localtime(first):%H:%M}" if first else f" · trading from {truck.trading_from:%H:%M}"
    ctx = _shell(request, "dashboard", sub=sub)
    ctx.update({
        "tiles": {
            "orders": len(orders), "live": len(live), "takings": takings,
            "preparing": sum(1 for o in orders if o.status == Order.Status.PREPARING),
            "ready": sum(1 for o in orders if o.status == Order.Status.READY),
            "avg_prep": avg_prep,
        },
        "live_orders": [o for o in reversed(orders) if o.status in LIVE],
        "next_labels": NEXT_LABELS,
        "attention": _attention(
            MenuItem.objects.filter(is_available=False),
            [s for s in slots if s.remaining == 0],
            ctx["flagged_count"],
        ),
        "windows": slots[:4],
        "latest_reviews": Review.objects.filter(is_hidden=False).select_related("menu_item", "user")[:3],
    })
    return render(request, "staff/dashboard.html", ctx)


def _buckets():
    live = _live_orders()
    return [
        {"key": key, "label": label, "next_label": NEXT_LABELS[key], "orders": [o for o in live if o.status == key]}
        for key, label in Order.Status.choices
        if key in NEXT_LABELS
    ]


def _board_context(request):
    return {
        "buckets": _buckets(),
        "collected": [o for o in _todays_orders().order_by("-created_at") if o.status == Order.Status.COLLECTED],
        "show_takings": is_manager(request.user),
        "queue_url": reverse("staff.queue"),
    }


@staff_member_required
def queue(request):
    today = timezone.localdate()
    ctx = _shell(request, "queue", title=f"Queue · {today:%a} {today.day} {today:%b}", sub="One button per transition. Nothing else moves an order.")
    ctx.update(_board_context(request))
    return render(request, "staff/queue.html", ctx)


@staff_member_required
def queue_partial(request):
    """The board alone."""
    return render(request, "staff/_queue_board.html", _board_context(request))


@staff_member_required
@require_POST
def advance(request, order_id):
    """Advance one order exactly one step along Order.FLOW. Posted from the
    queue, the dashboard and the order drawer alike; `next` says which."""
    order = get_object_or_404(Order, pk=order_id)
    back = _safe_next(request, reverse("staff.queue"))
    if order.advance() is None:
        return _done(request, f"Order #{order.id} is already {order.get_status_display().lower()}.", back, ok=False)
    updates = {
        "#queue-board": _fragment(request, "staff/_queue_board.html", _board_context(request)),
        "#dash-live": _fragment(request, "staff/_dash_live.html", {"live_orders": _live_orders(), "next_labels": NEXT_LABELS}),
        f"#order-row-{order.id}": _fragment(request, "staff/_order_row.html", {"order": order, "show_takings": is_manager(request.user)}),
        "#nav-badge-live": _fragment(request, "staff/_nav_badge.html", {"key": "live", "count": _live_count()}),
        "#drawer-root": "",
    }
    return _done(request, f"#{order.id} → {order.get_status_display()}", back, updates)

ORDER_FILTERS = [("all", "All")] + [(key, label) for key, label in Order.Status.choices]


def _orders_page(request, drawer_html=None):
    status = request.GET.get("status", "all")
    q = request.GET.get("q", "").strip()
    rows = _todays_orders().order_by("-created_at")
    if status != "all":
        rows = rows.filter(status=status)
    if q:
        rows = rows.filter(Q(customer_name__icontains=q) | Q(phone__icontains=q) | Q(code__icontains=q) | Q(id__icontains=q))
    ctx = _shell(request, "orders")
    ctx.update({"orders": rows, "filters": ORDER_FILTERS, "status": status, "q": q, "drawer_html": drawer_html})
    return render(request, "staff/orders.html", ctx)


@staff_member_required
def orders(request):
    return _orders_page(request)


@staff_member_required
def order(request, order_id):
    """The order drawer. staff.js fetches it and slides it over the table;
    without JS the same URL renders the table WITH the drawer open."""
    order = get_object_or_404(Order.objects.select_related("slot").prefetch_related("items"), pk=order_id)
    html = _fragment(request, "staff/_order_drawer.html", {"order": order, "next_labels": NEXT_LABELS, "show_takings": is_manager(request.user)})
    if _is_fetch(request):
        return JsonResponse({"html": html})
    return _orders_page(request, drawer_html=html)


def _sold_today():
    """{menu_item_id: quantity} for today's non-cancelled orders."""
    rows = (Order.objects.filter(created_at__date=timezone.localdate()).exclude(status=Order.Status.CANCELLED)
            .values("items__menu_item_id").annotate(qty=Sum("items__quantity")))
    return {r["items__menu_item_id"]: r["qty"] or 0 for r in rows}


def _item_row_ctx(request, item, sold=None):
    return {"item": item, "sold": (sold if sold is not None else _sold_today()).get(item.id, 0), "show_takings": is_manager(request.user)}


def _items_page(request, drawer_html=None):
    items = MenuItem.objects.select_related("category")
    sold = _sold_today()
    ctx = _shell(request, "items")
    ctx.update({"rows": [_item_row_ctx(request, item, sold) for item in items], "drawer_html": drawer_html})
    return render(request, "staff/items.html", ctx)


@staff_member_required
def items(request):
    return _items_page(request)


@manager_required
@require_POST
def item_price(request, item_id):
    """Inline price update (manager only)."""
    item = get_object_or_404(MenuItem, pk=item_id)
    try:
        price = Decimal(request.POST.get("price", "")).quantize(Decimal("0.01"))
        if price < 0:
            raise InvalidOperation
    except InvalidOperation:
        return _done(request, "That isn't a price.", reverse("staff.items"), {f"#item-row-{item.id}": _fragment(request, "staff/_item_row.html", _item_row_ctx(request, item))}, ok=False)
    item.price = price
    item.save(update_fields=["price"])
    return _done(request, f"{item.name} now R{item.price}", reverse("staff.items"), {f"#item-row-{item.id}": _fragment(request, "staff/_item_row.html", _item_row_ctx(request, item))})


@staff_member_required
@require_POST
def item_toggle(request, item_id):
    item = get_object_or_404(MenuItem, pk=item_id)
    item.is_available = not item.is_available
    item.save(update_fields=["is_available"])
    msg = f"{item.name} {'back on the menu' if item.is_available else 'marked sold out'}"
    return _done(request, msg, reverse("staff.items"), {f"#item-row-{item.id}": _fragment(request, "staff/_item_row.html", _item_row_ctx(request, item))})


@manager_required
def item_edit(request, item_id):
    """The item drawer: GET renders it (fetched by staff.js, or inline without
    JS); POST saves the whole record through MenuItemForm."""
    item = get_object_or_404(MenuItem.objects.select_related("category"), pk=item_id)
    form = MenuItemForm(request.POST or None, instance=item)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            return _done(request, f"{item.name} saved", reverse("staff.items"), {f"#item-row-{item.id}": _fragment(request, "staff/_item_row.html", _item_row_ctx(request, item)), "#drawer-root": ""})
        if _is_fetch(request):
            return JsonResponse({"ok": False, "message": "Check the highlighted fields.", "html": _fragment(request, "staff/_item_drawer.html", {"item": item, "form": form, "categories": Category.objects.all()})}, status=400)
    html = _fragment(request, "staff/_item_drawer.html", {"item": item, "form": form, "categories": Category.objects.all()})
    if _is_fetch(request):
        return JsonResponse({"html": html})
    return _items_page(request, drawer_html=html)


def _options_url(food):
    return reverse("staff.options") + f"?food={food.slug}"


def _group_ctx(group):
    return {"group": group, "options": group.options.all()}


def _groups_html(request, food):
    return _fragment(request, "staff/_option_groups.html", {"food": food, "groups": food.option_groups.prefetch_related("options")})


@manager_required
def options(request):
    dishes = list(MenuItem.objects.all())
    slug = request.GET.get("food")
    food = next((d for d in dishes if d.slug == slug), dishes[0] if dishes else None)
    ctx = _shell(request, "options")
    ctx.update({"dishes": dishes, "food": food, "groups": food.option_groups.prefetch_related("options") if food else []})
    return render(request, "staff/options.html", ctx)


@manager_required
@require_POST
def group_add(request, item_id):
    food = get_object_or_404(MenuItem, pk=item_id)
    last = food.option_groups.order_by("-sort_order").first()
    OptionGroup.objects.create(food=food, name="New group", sort_order=(last.sort_order + 1) if last else 0)
    return _done(request, "Group added — give it a name", _options_url(food), {"#groups-list": _groups_html(request, food)})


@manager_required
@require_POST
def group_update(request, group_id):
    """Update whichever group fields were posted."""
    group = get_object_or_404(OptionGroup.objects.select_related("food"), pk=group_id)
    fields = []
    if "name" in request.POST:
        group.name = request.POST["name"].strip()[:60] or group.name
        fields.append("name")
    if "required" in request.POST:
        group.required = request.POST["required"] == "1"
        fields.append("required")
    if "max_choices" in request.POST:
        try:
            group.max_choices = min(max(int(request.POST["max_choices"]), 1), 6)
        except ValueError:
            pass
        else:
            fields.append("max_choices")
    if fields:
        group.save(update_fields=fields)
    label = "Required" if group.required else "Optional"
    msg = f"{group.name}: {label}" if "required" in request.POST else f"{group.name} saved"
    return _done(request, msg, _options_url(group.food), {f"#group-{group.id}": _fragment(request, "staff/_option_group.html", _group_ctx(group))})


@manager_required
@require_POST
def group_delete(request, group_id):
    group = get_object_or_404(OptionGroup.objects.select_related("food"), pk=group_id)
    food, name, gid = group.food, group.name, group.id
    group.delete()
    return _done(request, f"Deleted “{name}”", _options_url(food), {f"#group-{gid}": ""})


@manager_required
@require_POST
def option_add(request, group_id):
    group = get_object_or_404(OptionGroup.objects.select_related("food"), pk=group_id)
    last = group.options.order_by("-sort_order").first()
    Option.objects.create(group=group, name="New option", sort_order=(last.sort_order + 1) if last else 0)
    return _done(request, "Option added", _options_url(group.food), {f"#group-{group.id}": _fragment(request, "staff/_option_group.html", _group_ctx(group))})


@manager_required
@require_POST
def option_update(request, option_id):
    """Name, price_delta, or the availability switch."""
    option = get_object_or_404(Option.objects.select_related("group__food"), pk=option_id)
    group = option.group
    fields = []
    if "name" in request.POST:
        option.name = request.POST["name"].strip()[:60] or option.name
        fields.append("name")
    if "price_delta" in request.POST:
        try:
            delta = Decimal(request.POST["price_delta"] or "0").quantize(Decimal("0.01"))
            if delta < 0:
                raise InvalidOperation
        except InvalidOperation:
            return _done(request, "That isn't a price.", _options_url(group.food), {f"#group-{group.id}": _fragment(request, "staff/_option_group.html", _group_ctx(group))}, ok=False)
        option.price_delta = delta
        fields.append("price_delta")
    if "toggle" in request.POST:
        option.is_available = not option.is_available
        fields.append("is_available")
    if fields:
        option.save(update_fields=fields)
    msg = f"{option.name} {'available' if option.is_available else 'unavailable'}" if "toggle" in request.POST else f"{option.name} saved"
    return _done(request, msg, _options_url(group.food), {f"#group-{group.id}": _fragment(request, "staff/_option_group.html", _group_ctx(group))})


@manager_required
@require_POST
def option_delete(request, option_id):
    option = get_object_or_404(Option.objects.select_related("group__food"), pk=option_id)
    group, name = option.group, option.name
    option.delete()
    return _done(request, f"Removed {name}", _options_url(group.food), {f"#group-{group.id}": _fragment(request, "staff/_option_group.html", _group_ctx(group))})

REVIEW_FILTERS = [("all", "All"), ("5", "5 star"), ("4", "4 star"), ("3", "3 star"), ("low", "1–2 star"), ("hidden", "Hidden")]


@manager_required
def reviews(request):
    pick = request.GET.get("rating", "all")
    rows = Review.objects.select_related("menu_item", "user")
    if pick == "hidden":
        rows = rows.filter(is_hidden=True)
    elif pick == "low":
        rows = rows.filter(rating__lte=2)
    elif pick in ("3", "4", "5"):
        rows = rows.filter(rating=int(pick))
    ctx = _shell(request, "reviews")
    ctx.update({"reviews": rows, "filters": REVIEW_FILTERS, "pick": pick})
    return render(request, "staff/reviews.html", ctx)


def _review_updates(request, review, html):
    return {f"#review-{review.id}": html, "#nav-badge-flagged": _fragment(request, "staff/_nav_badge.html", {"key": "flagged", "count": _flagged_count()})}


@manager_required
@require_POST
def review_hide(request, review_id):
    """Hide ↔ show again. Hidden rows leave the dish page and the average
    (see MenuItem.average_rating) but stay in the table, visibly parked."""
    review = get_object_or_404(Review.objects.select_related("menu_item", "user"), pk=review_id)
    review.is_hidden = not review.is_hidden
    review.save(update_fields=["is_hidden"])
    msg = "Review hidden from the dish page" if review.is_hidden else "Review restored"
    return _done(request, msg, reverse("staff.reviews"), _review_updates(request, review, _fragment(request, "staff/_review_card.html", {"review": review})))


@manager_required
@require_POST
def review_delete(request, review_id):
    review = get_object_or_404(Review, pk=review_id)
    rid = review.id
    review.delete()
    review.id = rid
    return _done(request, "Review deleted", reverse("staff.reviews"), _review_updates(request, review, ""))


def _truck_updates(request, truck):
    return {
        "#truck-live": _fragment(request, "staff/_truck_live.html", {"truck": truck}),
        "#truck-preview": _fragment(request, "staff/_truck_preview.html", {"truck": truck}),
        "#header-trading": _fragment(request, "staff/_trading_pill.html", {"truck": truck}),
    }


@manager_required
def truck(request):
    truck = TruckLocation.current()
    form = TruckForm(request.POST or None, instance=truck)
    if request.method == "POST" and form.is_valid():
        truck = form.save()
        return _done(request, "Truck saved — the context bar already shows it", reverse("staff.truck"))
    ctx = _shell(request, "truck")
    ctx.update({"form": form, "truck": truck})
    return render(request, "staff/truck.html", ctx)


@manager_required
@require_POST
def truck_live(request):
    """The is_live switch on its own POST: the whole storefront flips between
    trading and closed on this one column, so it gets its own deliberate tap."""
    truck = TruckLocation.current()
    truck.is_live = not truck.is_live
    truck.save()
    msg = "Trading — checkout is open" if truck.is_live else "Closed — checkout replaced by the closed panel"
    return _done(request, msg, reverse("staff.truck"), _truck_updates(request, truck))


def _slot_row(request, slot):
    return _fragment(request, "staff/_slot_row.html", {"slot": slot, "now": timezone.now()})


@manager_required
def slots(request):
    now = timezone.now()
    truck = TruckLocation.current()
    ctx = _shell(request, "slots")
    ctx.update({"slots": _todays_slots(truck, now), "now": now, "truck": truck})
    return render(request, "staff/slots.html", ctx)


@manager_required
@require_POST
def slot_add(request):
    """One more 15-minute window after the last one today, at the truck's capacity."""
    now = timezone.now()
    truck = TruckLocation.current()
    existing = _todays_slots(truck, now)
    if existing:
        start = existing[-1].start + timedelta(minutes=SLOT_MINUTES)
    else:
        start = (now + timedelta(minutes=truck.ready_minutes)).replace(second=0, microsecond=0)
        start += timedelta(minutes=(-start.minute) % SLOT_MINUTES)
    slot, created = PickupSlot.objects.get_or_create(start=start, defaults={"capacity": truck.slot_capacity})
    rows = list(PickupSlot.objects.filter(start__gt=now - timedelta(minutes=SLOT_MINUTES), start__lte=start))
    return _done(request, f"{slot.label()} added" if created else f"{slot.label()} already exists", reverse("staff.slots"), {"#slots-list": _fragment(request, "staff/_slot_rows.html", {"slots": rows, "now": now})})


@manager_required
@require_POST
def slot_capacity(request, slot_id):
    """±1 on the stepper."""
    slot = get_object_or_404(PickupSlot, pk=slot_id)
    delta = 1 if request.POST.get("delta") == "1" else -1
    slot.capacity = min(max(slot.capacity + delta, slot.taken, 1), SLOT_CAPACITY_CEILING)
    slot.save(update_fields=["capacity"])
    msg = f"{slot.label()}: {'full — off checkout' if slot.remaining == 0 else f'{slot.remaining} left'}"
    return _done(request, msg, reverse("staff.slots"), {f"#slot-{slot.id}": _slot_row(request, slot)})


@manager_required
@require_POST
def slot_close(request, slot_id):
    """Delete an empty window, or cap a used one at its current count."""
    slot = get_object_or_404(PickupSlot, pk=slot_id)
    label, sid = slot.label(), slot.id
    if slot.taken == 0:
        slot.delete()
        return _done(request, f"{label} closed", reverse("staff.slots"), {f"#slot-{sid}": ""})
    slot.capacity = slot.taken
    slot.save(update_fields=["capacity"])
    return _done(request, f"{label} closed to new orders — {slot.taken} already booked", reverse("staff.slots"), {f"#slot-{sid}": _slot_row(request, slot)})


def _people():
    return User.objects.filter(is_staff=True).prefetch_related("groups").order_by("-is_active", "first_name", "username")


def _people_rows(request):
    return {"people": [(p, role_of(p)) for p in _people()], "me": request.user}


@manager_required
def people(request):
    ctx = _shell(request, "staff")
    ctx.update(_people_rows(request))
    ctx["form"] = InviteForm()
    return render(request, "staff/people.html", ctx)


@manager_required
@require_POST
def person_toggle(request, user_id):
    """Suspend ↔ restore = is_active. Django refuses a login for an inactive
    user everywhere, so nothing else needs to check."""
    person = get_object_or_404(User, pk=user_id, is_staff=True)
    if person == request.user:
        return _done(request, "You can't suspend yourself.", reverse("staff.people"), ok=False)
    person.is_active = not person.is_active
    person.save(update_fields=["is_active"])
    msg = f"{person.get_full_name() or person.username} {'restored' if person.is_active else 'suspended'}"
    return _done(request, msg, reverse("staff.people"), {f"#person-{person.id}": _fragment(request, "staff/_person_row.html", {"person": person, "person_role": role_of(person), "me": request.user})})


@manager_required
@require_POST
def invite(request):
    """Create a staff account with no usable password; a manager sets it from admin."""
    form = InviteForm(request.POST)
    if not form.is_valid():
        msg = "Give them a name first" if "name" in form.errors else next(iter(form.errors.values()))[0]
        return _done(request, msg, reverse("staff.people"), ok=False)
    name, email, role = form.cleaned_data["name"], form.cleaned_data["email"], form.cleaned_data["role"]
    base = email.split("@")[0][:140] or "staff"
    username, n = base, 1
    while User.objects.filter(username=username).exists():
        n += 1
        username = f"{base}{n}"
    first, _, last = name.partition(" ")
    person = User.objects.create_user(username, email, None, first_name=first, last_name=last, is_staff=True)
    if role in MANAGER_GROUPS:
        group, _ = Group.objects.get_or_create(name=role)
        person.groups.add(group)
    return _done(request, f"{name} added as {role}", reverse("staff.people"), {"#people-list": _fragment(request, "staff/_person_rows.html", _people_rows(request))})
