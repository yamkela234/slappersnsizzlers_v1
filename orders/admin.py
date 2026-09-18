from django.contrib import admin

from .models import Order, OrderItem, PickupSlot


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("name_snapshot", "price_snapshot", "options_snapshot", "line_total")
    fields = ("menu_item", "name_snapshot", "options_snapshot", "price_snapshot", "quantity", "line_total")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "customer_name", "status", "slot", "total", "created_at")
    list_filter = ("status",)
    list_editable = ("status",)
    search_fields = ("customer_name", "phone", "code")
    inlines = [OrderItemInline]
    readonly_fields = ("code",)


@admin.register(PickupSlot)
class PickupSlotAdmin(admin.ModelAdmin):
    list_display = ("start", "capacity", "taken")
    list_editable = ("capacity",)
    ordering = ("-start",)
