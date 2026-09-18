import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

SLOT_MINUTES = 15


class PickupSlot(models.Model):
    """A 15-minute collection window with a capacity."""

    start = models.DateTimeField(unique=True)
    capacity = models.PositiveSmallIntegerField(default=8)
    taken = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["start"]

    def __str__(self):
        return self.label()

    @property
    def end(self):
        return self.start + timedelta(minutes=SLOT_MINUTES)

    @property
    def remaining(self):
        return max(self.capacity - self.taken, 0)

    def label(self):
        """"18:45 – 19:00" in the truck's local time."""
        return f"{timezone.localtime(self.start):%H:%M} – {timezone.localtime(self.end):%H:%M}"

    def relative_label(self, now=None):
        """"In 22 min"."""
        minutes = int((self.start - (now or timezone.now())).total_seconds() // 60)
        return f"In {max(minutes, 0)} min"

    @classmethod
    def upcoming(cls, truck, now=None, limit=6):
        """Upcoming windows with room, created from the trading hours if needed."""
        now = now or timezone.now()
        first = now + timedelta(minutes=truck.ready_minutes)
        first = first.replace(second=0, microsecond=0)
        first += timedelta(minutes=(-first.minute) % SLOT_MINUTES)
        closing = truck.closes_at(now)
        starts = []
        start = first
        while start < closing and len(starts) < limit * 2:
            starts.append(start)
            start += timedelta(minutes=SLOT_MINUTES)
        for start in starts:
            cls.objects.get_or_create(start=start, defaults={"capacity": truck.slot_capacity})
        return [slot for slot in cls.objects.filter(start__in=starts) if slot.remaining > 0][:limit]


class Order(models.Model):
    """One placed order: who it's for, where it is in the kitchen pipeline,
    when they're collecting, and what it cost at the moment it was placed."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PREPARING = "preparing", "Preparing"
        READY = "ready", "Ready"
        COLLECTED = "collected", "Collected"
        CANCELLED = "cancelled", "Cancelled"

    FLOW = ["pending", "preparing", "ready", "collected"]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    customer_name = models.CharField(max_length=80)
    phone = models.CharField(max_length=20)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    code = models.CharField(max_length=4, blank=True)
    slot = models.ForeignKey(
        PickupSlot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    tip = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=8, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    preparing_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.id} — {self.customer_name}"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = f"{secrets.randbelow(9000) + 1000}"
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("orders.show", kwargs={"order_id": self.id})

    def is_live(self):
        """Still moving through the kitchen."""
        return self.status in (self.Status.PENDING, self.Status.PREPARING, self.Status.READY)

    def next_status(self):
        """The one transition the staff queue offers, or None at the end of the flow."""
        if self.status not in self.FLOW:
            return None
        index = self.FLOW.index(self.status)
        return self.FLOW[index + 1] if index + 1 < len(self.FLOW) else None

    def advance(self):
        """Move one step along FLOW, stamping the timestamp. Returns the new status or None."""
        nxt = self.next_status()
        if nxt is None:
            return None
        self.status = nxt
        fields = ["status"]
        if nxt == self.Status.PREPARING:
            self.preparing_at = timezone.now()
            fields.append("preparing_at")
        elif nxt == self.Status.READY:
            self.ready_at = timezone.now()
            fields.append("ready_at")
        self.save(update_fields=fields)
        return nxt

    def prep_seconds(self):
        """How long the grill actually took, or None until both stamps exist."""
        if self.preparing_at and self.ready_at:
            return (self.ready_at - self.preparing_at).total_seconds()
        return None

    def window_label(self):
        """"Ready in about 15 min" for ASAP, "Collect 18:45 – 19:00" for a slot."""
        if self.slot_id:
            return f"Collect {self.slot.label()}"
        return "Ready in about 15 min"

    def goods_total(self):
        return self.total - self.tip


class OrderItem(models.Model):
    """One line on an order: N × a dish, with its choices, frozen at the price it had that day."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.PROTECT,
        related_name="order_lines",
    )
    name_snapshot = models.CharField(max_length=80)
    price_snapshot = models.DecimalField(max_digits=7, decimal_places=2)
    quantity = models.PositiveSmallIntegerField()
    options_snapshot = models.CharField(
        max_length=200,
        blank=True,
    )
    note = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.quantity} × {self.name_snapshot}" + (f" ({self.options_snapshot})" if self.options_snapshot else "")

    def line_total(self):
        """quantity × frozen unit price."""
        return self.price_snapshot * self.quantity
