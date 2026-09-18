from django.contrib import admin

from .models import Category, MenuItem, Option, OptionGroup, Review


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order")
    prepopulated_fields = {"slug": ("name",)}


class OptionGroupInline(admin.TabularInline):
    model = OptionGroup
    extra = 0
    fields = ("name", "required", "max_choices", "sort_order")
    show_change_link = True


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "is_available", "created_at")
    list_filter = ("category", "is_available")
    list_editable = ("price", "is_available")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [OptionGroupInline]


class OptionInline(admin.TabularInline):
    model = Option
    extra = 0
    fields = ("name", "price_delta", "sort_order", "is_available")


@admin.register(OptionGroup)
class OptionGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "food", "required", "max_choices")
    list_filter = ("required",)
    list_select_related = ("food",)
    inlines = [OptionInline]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("menu_item", "user", "rating", "created_at")
    list_filter = ("rating",)
    search_fields = ("comment", "user__username", "menu_item__name")
    list_select_related = ("menu_item", "user")
    readonly_fields = ("created_at", "updated_at")
