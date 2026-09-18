from decimal import Decimal
from hashlib import sha1

from menu.models import MenuItem, Option

CART_SESSION_KEY = "cart"

NOTE_MAX_LENGTH = 200

MAX_QTY = 10


def line_key(item_id, option_ids=(), note=""):
    """Session key for one cart line: item id + sorted option ids + note digest."""
    ids = "-".join(str(i) for i in sorted(int(i) for i in option_ids)) or "none"
    note_digest = sha1(note.strip().encode()).hexdigest()[:8] if note.strip() else "0"
    return f"{item_id}:{ids}:{note_digest}"


def get_cart(request):
    """Return the session cart, creating it if needed."""
    return request.session.setdefault(CART_SESSION_KEY, {})


def _normalise(key, value):
    """Coerce a stored line into the current shape, or None if it can't be read."""
    if isinstance(value, int):
        return {"item_id": str(key), "qty": value, "options": [], "note": ""}
    if isinstance(value, dict) and "item_id" in value and "qty" in value:
        options = value.get("options", [])
        return {
            "item_id": str(value["item_id"]),
            "qty": int(value["qty"]),
            "options": [int(i) for i in options if str(i).isdigit()],
            "note": value.get("note", ""),
        }
    return None


def iter_lines(request):
    """Every usable line as (key, line dict) pairs, with junk entries skipped."""
    for key, value in get_cart(request).items():
        line = _normalise(key, value)
        if line:
            yield key, line


def add_item(request, item_id, qty=1, option_ids=(), note=""):
    """Add `qty` of an item (with its chosen options and note) to the cart.
    Returns the line key, so a caller can link straight back to the line."""
    cart = get_cart(request)
    note = note.strip()[:NOTE_MAX_LENGTH]
    option_ids = sorted({int(i) for i in option_ids})
    key = line_key(item_id, option_ids, note)
    existing = _normalise(key, cart[key]) if key in cart else None
    cart[key] = {
        "item_id": str(item_id),
        "qty": min(MAX_QTY, (existing["qty"] if existing else 0) + qty),
        "options": option_ids,
        "note": note,
    }
    request.session.modified = True
    return key


def set_quantity(request, key, qty):
    """Set a line's quantity (1-10). Zero or less removes the line."""
    cart = get_cart(request)
    line = _normalise(key, cart[key]) if key in cart else None
    if line is None:
        return
    if qty < 1:
        cart.pop(key, None)
    else:
        line["qty"] = min(MAX_QTY, qty)
        cart[key] = line
    request.session.modified = True


def remove_item(request, key):
    """Drop one LINE from the cart entirely (all its quantity, not minus one)."""
    cart = get_cart(request)
    cart.pop(str(key), None)
    request.session.modified = True


def clear_cart(request):
    """Empty the cart."""
    request.session[CART_SESSION_KEY] = {}
    request.session.modified = True


def count_items(request):
    """Total number of items across every line."""
    return sum(line["qty"] for _, line in iter_lines(request))


def cart_summary(request):
    """Return (rows, grand_total) with live prices from the database."""
    lines = list(iter_lines(request))
    items = MenuItem.objects.in_bulk([line["item_id"] for _, line in lines])
    option_ids = {i for _, line in lines for i in line["options"]}
    options = Option.objects.filter(id__in=option_ids).select_related("group").in_bulk()
    rows = []
    grand_total = Decimal("0.00")
    for key, line in lines:
        item = items.get(int(line["item_id"])) if line["item_id"].isdigit() else None
        if item is None:
            continue
        chosen = [options[i] for i in line["options"] if i in options and options[i].group.food_id == item.id]
        unit_price = item.price + sum((o.price_delta for o in chosen), Decimal("0.00"))
        line_total = unit_price * line["qty"]
        rows.append({
            "key": key,
            "item": item,
            "quantity": line["qty"],
            "options": chosen,
            "choices": [o for o in chosen if o.group.required],
            "extras": [o for o in chosen if not o.group.required],
            "note": line["note"],
            "unit_price": unit_price,
            "line_total": line_total,
        })
        grand_total += line_total
    return rows, grand_total


def options_label(options):
    """Comma-separated option names, used for order snapshots."""
    return ", ".join(o.name for o in options)
