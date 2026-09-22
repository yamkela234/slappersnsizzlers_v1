from datetime import time
from decimal import Decimal

from django.core.management.base import BaseCommand

from home.models import TruckLocation
from menu.models import Category, MenuItem, Option, OptionGroup

SAUCES = ["Peri-Peri", "BBQ", "Sweet Chilli", "Garlic Ranch", "Lemon & Herb"]

EXTRAS = [("Bacon bits", "12.00"), ("Extra ranch pot", "12.00"), ("Cheese sauce", "9.00")]

MENU = [
    ("Burgers & Dogs", "burgers-dogs", 1, [
        ("Sizzler Burger", "sizzler-burger", "Double beef patty, cheese, bacon and the special sauce we won't tell you about.", "79.99", "burger.jpg", 12, False, ["BBQ", "Garlic Ranch", "Peri-Peri"], True),
        ("Loaded Hotdog", "loaded-hotdog", "Premium sausage with cheese, jalapeños and crisp onions.", "59.99", "loaded_hotdog.jpg", 10, True, ["BBQ", "Sweet Chilli"], True),
    ]),
    ("Wings", "wings", 2, [
        ("Buffalo Wings Combo", "buffalo-wings-combo", "Eight spicy wings, ranch dip and a basket of fries. The one that built the queue we're trying to get rid of.", "89.99", "wings_combo.jpg", 15, True, SAUCES, True),
        ("Classic Wings", "classic-wings", "Crispy fried wings tossed in the sauce of your choosing.", "69.99", "wingss.jpg", 15, False, SAUCES, True),
    ]),
    ("Sides", "sides", 3, [
        ("Loaded Fries", "loaded-fries", "Golden fries under cheese sauce and toppings. No decisions required.", "49.99", "loaded_fries.jpg", 8, False, None, False),
    ]),
]


class Command(BaseCommand):
    help = "Seed the menu with categories, items, option groups, images and the truck location (idempotent)."

    def handle(self, *args, **options):
        for category_name, category_slug, sort_order, items in MENU:
            category, _ = Category.objects.get_or_create(
                slug=category_slug,
                defaults={"name": category_name, "sort_order": sort_order},
            )
            for name, slug, description, price, image_name, prep_minutes, is_spicy, sauces, extras in items:
                item, created = MenuItem.objects.get_or_create(
                    slug=slug,
                    defaults={"category": category, "name": name, "description": description, "price": Decimal(price), "prep_minutes": prep_minutes, "is_spicy": is_spicy},
                )
                if sauces:
                    group, group_created = OptionGroup.objects.get_or_create(food=item, name="Choose Sauce", defaults={"required": True, "max_choices": 1, "sort_order": 1})
                    if group_created:
                        for i, sauce in enumerate(sauces, start=1):
                            Option.objects.create(group=group, name=sauce, price_delta=0, sort_order=i)
                if extras:
                    group, group_created = OptionGroup.objects.get_or_create(food=item, name="Add Extras", defaults={"required": False, "max_choices": len(EXTRAS), "sort_order": 2})
                    if group_created:
                        for i, (extra, delta) in enumerate(EXTRAS, start=1):
                            Option.objects.create(group=group, name=extra, price_delta=Decimal(delta), sort_order=i)
                if item.static_image != image_name:
                    MenuItem.objects.filter(pk=item.pk).update(static_image=image_name)
                self.stdout.write(f"{'created' if created else 'exists '}: {item.name}")
        truck, truck_created = TruckLocation.objects.get_or_create(
            pk=1,
            defaults={"name": "Summer Food Festival", "zone": "4", "trading_from": time(11, 0), "trading_until": time(22, 0), "is_live": True, "ready_minutes": 15, "slot_capacity": 8},
        )
        self.stdout.write(f"{'created' if truck_created else 'exists '}: truck at {truck}")
        self.stdout.write(self.style.SUCCESS("Menu seeded."))
