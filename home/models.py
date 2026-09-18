from datetime import datetime, time, timedelta

from django.db import models
from django.utils import timezone


class TruckLocation(models.Model):
    """Where the truck is trading and when. One row."""

    name = models.CharField(max_length=80)
    zone = models.CharField(max_length=20, blank=True)
    trading_from = models.TimeField(default=time(11, 0))
    trading_until = models.TimeField(default=time(22, 0))
    is_live = models.BooleanField(default=True)
    next_return = models.DateTimeField(null=True, blank=True)
    ready_minutes = models.PositiveSmallIntegerField(default=15)
    slot_capacity = models.PositiveSmallIntegerField(default=8)

    class Meta:
        verbose_name = "truck location"

    def __str__(self):
        return self.name + (f" · Zone {self.zone}" if self.zone else "")

    def is_trading_at(self, now):
        """True when the truck is live AND `now` (an aware datetime) falls inside the hours."""
        if not self.is_live:
            return False
        t = timezone.localtime(now).time()
        if self.trading_until <= self.trading_from:
            return t >= self.trading_from or t < self.trading_until
        return self.trading_from <= t < self.trading_until

    @property
    def is_trading(self):
        return self.is_trading_at(timezone.now())

    def next_opening(self, now=None):
        """When the closed bar should say we're back: the explicit next_return if
        it's in the future, else the next occurrence of trading_from."""
        now = timezone.localtime(now or timezone.now())
        if self.next_return and self.next_return > now:
            return timezone.localtime(self.next_return)
        candidate = timezone.make_aware(datetime.combine(now.date(), self.trading_from), now.tzinfo)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    def closes_at(self, now=None):
        """Today's closing moment as an aware datetime."""
        now = timezone.localtime(now or timezone.now())
        closing = timezone.make_aware(datetime.combine(now.date(), self.trading_until), now.tzinfo)
        if self.trading_until <= self.trading_from:
            closing += timedelta(days=1)
        return closing

    @classmethod
    def current(cls):
        """The configured truck, or an always-open placeholder if none exists."""
        truck = cls.objects.order_by("pk").first()
        if truck is None:
            truck = cls(name="Slappers n Sizzlers", zone="", trading_from=time(0, 0), trading_until=time(0, 0), is_live=True)
        return truck
