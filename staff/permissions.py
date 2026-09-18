from functools import wraps

from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied

MANAGER_GROUPS = ("Manager", "Owner")


def role_of(user):
    """Owner, Manager or Crew, for the sidebar."""
    if user.is_superuser:
        return "Owner"
    names = set(user.groups.values_list("name", flat=True))
    for name in MANAGER_GROUPS:
        if name in names:
            return name
    return "Crew"


def is_manager(user):
    return role_of(user) != "Crew"


def manager_required(view):
    """staff_member_required plus the manager group check."""

    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not is_manager(request.user):
            raise PermissionDenied("Manager access only.")
        return view(request, *args, **kwargs)

    return staff_member_required(_wrapped)
