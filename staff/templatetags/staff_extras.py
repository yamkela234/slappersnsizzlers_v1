from django import template

register = template.Library()


@register.filter
def initials(user):
    """"Thandi Mokoena" → "TM"; falls back to the username. The avatar in
    the sidebar footer and the Staff table."""
    name = (user.get_full_name() or user.username or "").strip()
    return "".join(part[0] for part in name.split()[:2]).upper() or "?"


@register.filter
def money(value):
    """Format a Decimal as R0.00."""
    if value is None:
        return "—"
    return f"R{value:.2f}"


@register.filter
def get_item(mapping, key):
    """Dictionary lookup by variable key."""
    return mapping.get(key, "")
