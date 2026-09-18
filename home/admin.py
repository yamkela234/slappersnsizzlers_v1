from django.contrib import admin

from .models import TruckLocation


@admin.register(TruckLocation)
class TruckLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "zone", "trading_from", "trading_until", "is_live", "ready_minutes", "slot_capacity")
    list_editable = ("is_live", "ready_minutes")
