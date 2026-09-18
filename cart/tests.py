from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from cart.utils import line_key
from home.models import TruckLocation
from menu.models import Category, MenuItem, Option, OptionGroup


class CartTestBase(TestCase):
    """Shared fixtures: two orderable menu items, plus one sold-out item."""

    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(name="Burgers", slug="burgers", sort_order=1)
        cls.burger = MenuItem.objects.create(
            category=cls.cat, name="Sizzler Burger", slug="sizzler-burger",
            price=Decimal("89.99"), is_available=True,
        )
        cls.wings = MenuItem.objects.create(
            category=cls.cat, name="Flame Wings", slug="flame-wings",
            price=Decimal("64.50"), is_available=True,
        )
        cls.sold_out = MenuItem.objects.create(
            category=cls.cat, name="Gatsby", slug="gatsby",
            price=Decimal("120.00"), is_available=False,
        )
        cls.sauce_group = OptionGroup.objects.create(food=cls.burger, name="Choose Sauce", required=False, max_choices=1, sort_order=1)
        cls.peri = Option.objects.create(group=cls.sauce_group, name="Peri-Peri", sort_order=1)
        cls.bbq = Option.objects.create(group=cls.sauce_group, name="BBQ", sort_order=2)
        cls.extras_group = OptionGroup.objects.create(food=cls.burger, name="Add Extras", required=False, max_choices=3, sort_order=2)
        cls.bacon = Option.objects.create(group=cls.extras_group, name="Bacon bits", price_delta=Decimal("12.00"), sort_order=1)
        cls.combo = MenuItem.objects.create(
            category=cls.cat, name="Wings Combo", slug="wings-combo",
            price=Decimal("89.99"), is_available=True,
        )
        cls.combo_group = OptionGroup.objects.create(food=cls.combo, name="Choose Sauce", required=True, max_choices=1)
        cls.combo_peri = Option.objects.create(group=cls.combo_group, name="Peri-Peri")
        cls.mystery_group = OptionGroup.objects.create(food=cls.sold_out, name="Secret", required=False)
        cls.mystery = Option.objects.create(group=cls.mystery_group, name="Mystery")

    def add(self, item, qty=None, options=None, note=None, **extra):
        data = {} if qty is None else {"quantity": qty}
        for option in options or []:
            data.setdefault(f"group-{option.group_id}", []).append(str(option.id))
        if note is not None:
            data["note"] = note
        data.update(extra)
        return self.client.post(reverse("cart.add", args=[item.id]), data)


class CartIndexTests(CartTestBase):
    def test_empty_cart_renders_empty_state(self):
        response = self.client.get(reverse("cart.index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your order is empty")
        self.assertContains(response, reverse("home.index") + "#menu")

    def test_cart_page_shows_items_line_totals_and_grand_total(self):
        self.add(self.burger, 2)
        self.add(self.wings, 1)
        response = self.client.get(reverse("cart.index"))
        self.assertContains(response, "Sizzler Burger")
        self.assertContains(response, "R179.98")
        self.assertContains(response, "R244.48")
        self.assertEqual(response.context["grand_total"], Decimal("244.48"))

    def test_deleted_item_disappears_from_summary_instead_of_crashing(self):
        self.add(self.burger, 1)
        self.burger.delete()
        response = self.client.get(reverse("cart.index"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["rows"], [])
        self.assertEqual(response.context["grand_total"], Decimal("0.00"))


class CartAddTests(CartTestBase):
    def test_add_requires_post(self):
        response = self.client.get(reverse("cart.add", args=[self.burger.id]))
        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_add_stores_string_key_in_session(self):
        self.add(self.burger, 1)
        cart = self.client.session["cart"]
        key = line_key(self.burger.id)
        self.assertIn(key, cart)
        self.assertNotIn(self.burger.id, cart)
        self.assertEqual(cart[key]["item_id"], str(self.burger.id))

    def test_add_same_item_twice_increments_instead_of_duplicating(self):
        self.add(self.burger, 2)
        self.add(self.burger, 3)
        cart = self.client.session["cart"]
        self.assertEqual(cart[line_key(self.burger.id)]["qty"], 5)
        self.assertEqual(len(cart), 1)

    def test_add_defaults_to_one_when_quantity_missing_or_garbage(self):
        self.add(self.burger)
        self.assertEqual(self.client.session["cart"][line_key(self.burger.id)]["qty"], 1)
        self.add(self.wings, "abc")
        self.assertEqual(self.client.session["cart"][line_key(self.wings.id)]["qty"], 1)

    def test_add_clamps_quantity_to_allowed_range(self):
        self.add(self.burger, 999)
        self.assertEqual(self.client.session["cart"][line_key(self.burger.id)]["qty"], 10)
        self.add(self.wings, -5)
        self.assertEqual(self.client.session["cart"][line_key(self.wings.id)]["qty"], 1)

    def test_add_redirects_to_item_page_with_message(self):
        response = self.add(self.burger, 2)
        self.assertRedirects(response, reverse("menu.show", args=[self.burger.slug]), fetch_redirect_response=False)
        followed = self.client.get(response.url)
        self.assertContains(followed, "Added 2 × Sizzler Burger")

    def test_add_unavailable_item_is_404_and_cart_untouched(self):
        response = self.add(self.sold_out, 1)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_add_unknown_id_is_404(self):
        response = self.client.post(reverse("cart.add", args=[99999]))
        self.assertEqual(response.status_code, 404)


class CartRemoveTests(CartTestBase):
    def test_remove_requires_post(self):
        self.add(self.burger, 1)
        response = self.client.get(reverse("cart.remove", args=[line_key(self.burger.id)]))
        self.assertEqual(response.status_code, 405)
        self.assertIn(line_key(self.burger.id), self.client.session["cart"])

    def test_remove_drops_the_line_and_redirects_to_cart(self):
        self.add(self.burger, 2)
        self.add(self.wings, 1)
        response = self.client.post(reverse("cart.remove", args=[line_key(self.burger.id)]))
        self.assertRedirects(response, reverse("cart.index"))
        cart = self.client.session["cart"]
        self.assertNotIn(line_key(self.burger.id), cart)
        self.assertIn(line_key(self.wings.id), cart)

    def test_remove_targets_one_line_not_every_line_of_that_dish(self):
        self.add(self.burger, 1, options=[self.peri])
        self.add(self.burger, 1, options=[self.bbq])
        self.client.post(reverse("cart.remove", args=[line_key(self.burger.id, [self.peri.id])]))
        cart = self.client.session["cart"]
        self.assertEqual(len(cart), 1)
        self.assertIn(line_key(self.burger.id, [self.bbq.id]), cart)

    def test_remove_line_not_in_cart_is_a_noop(self):
        response = self.client.post(reverse("cart.remove", args=[line_key(self.burger.id)]))
        self.assertEqual(response.status_code, 302)


class CartOptionTests(CartTestBase):
    """Option groups: line keys, required groups, paid extras and notes."""

    def test_chosen_option_ids_are_stored_on_the_line(self):
        self.add(self.burger, 1, options=[self.peri])
        line = self.client.session["cart"][line_key(self.burger.id, [self.peri.id])]
        self.assertEqual(line["options"], [self.peri.id])

    def test_same_dish_with_different_sauces_makes_two_lines(self):
        self.add(self.burger, 1, options=[self.peri])
        self.add(self.burger, 2, options=[self.bbq])
        cart = self.client.session["cart"]
        self.assertEqual(len(cart), 2)
        self.assertEqual(cart[line_key(self.burger.id, [self.peri.id])]["qty"], 1)
        self.assertEqual(cart[line_key(self.burger.id, [self.bbq.id])]["qty"], 2)

    def test_same_dish_same_options_and_note_still_merges(self):
        self.add(self.burger, 1, options=[self.bbq, self.bacon], note="extra crispy")
        self.add(self.burger, 2, options=[self.bacon, self.bbq], note="extra crispy")
        cart = self.client.session["cart"]
        self.assertEqual(len(cart), 1)
        self.assertEqual(cart[line_key(self.burger.id, [self.bbq.id, self.bacon.id], "extra crispy")]["qty"], 3)

    def test_required_group_blocks_the_add(self):
        response = self.add(self.combo, 1)
        self.assertRedirects(response, self.combo.get_absolute_url(), fetch_redirect_response=False)
        self.assertEqual(self.client.session.get("cart", {}), {})
        self.add(self.combo, 1, options=[self.combo_peri])
        self.assertIn(line_key(self.combo.id, [self.combo_peri.id]), self.client.session["cart"])

    def test_option_from_another_dish_is_ignored(self):
        self.add(self.burger, 1, **{f"group-{self.mystery_group.id}": str(self.mystery.id)})
        self.assertIn(line_key(self.burger.id), self.client.session["cart"])

    def test_unavailable_option_is_ignored(self):
        self.peri.is_available = False
        self.peri.save()
        self.add(self.burger, 1, options=[self.peri])
        self.assertIn(line_key(self.burger.id), self.client.session["cart"])

    def test_too_many_choices_for_a_group_is_refused(self):
        response = self.add(self.burger, 1, options=[self.peri, self.bbq])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_paid_extra_moves_the_unit_price_and_totals(self):
        self.add(self.burger, 2, options=[self.bacon])
        response = self.client.get(reverse("cart.index"))
        self.assertEqual(response.context["rows"][0]["unit_price"], Decimal("101.99"))
        self.assertEqual(response.context["grand_total"], Decimal("203.98"))
        self.assertContains(response, "Bacon bits")
        self.assertContains(response, "R101.99 each")

    def test_note_is_trimmed_and_clipped_to_the_order_column_length(self):
        self.add(self.burger, 1, note="   no onions   ")
        self.assertEqual(self.client.session["cart"][line_key(self.burger.id, [], "no onions")]["note"], "no onions")
        self.add(self.wings, 1, note="x" * 500)
        self.assertEqual(len(self.client.session["cart"][line_key(self.wings.id, [], "x" * 200)]["note"]), 200)

    def test_options_and_note_appear_on_the_cart_page(self):
        self.add(self.burger, 1, options=[self.bbq], note="no onions")
        response = self.client.get(reverse("cart.index"))
        self.assertContains(response, "BBQ")
        self.assertContains(response, "no onions")

    def test_add_honours_a_safe_next_and_ignores_an_offsite_one(self):
        response = self.add(self.burger, 1, next="/#menu")
        self.assertRedirects(response, "/#menu", fetch_redirect_response=False)
        response = self.add(self.burger, 1, next="https://evil.example/")
        self.assertRedirects(response, self.burger.get_absolute_url(), fetch_redirect_response=False)

    def test_closed_truck_refuses_new_lines(self):
        TruckLocation.objects.create(name="Festival", is_live=False)
        response = self.add(self.burger, 1)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_legacy_sauce_shaped_line_still_renders(self):
        session = self.client.session
        session["cart"] = {"7:bbq:0": {"item_id": self.burger.id, "qty": 2, "sauce": "BBQ", "note": "hot"}}
        session.save()
        response = self.client.get(reverse("cart.index"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["grand_total"], Decimal("179.98"))
        self.assertContains(response, "hot")


class CartUpdateTests(CartTestBase):
    """Quantity steppers on the cart page."""

    def test_update_sets_the_new_quantity(self):
        self.add(self.burger, 2)
        response = self.client.post(reverse("cart.update", args=[line_key(self.burger.id)]), {"qty": 5})
        self.assertRedirects(response, reverse("cart.index"))
        self.assertEqual(self.client.session["cart"][line_key(self.burger.id)]["qty"], 5)

    def test_update_clamps_to_ten(self):
        self.add(self.burger, 2)
        self.client.post(reverse("cart.update", args=[line_key(self.burger.id)]), {"qty": 99})
        self.assertEqual(self.client.session["cart"][line_key(self.burger.id)]["qty"], 10)

    def test_update_to_zero_removes_the_line(self):
        self.add(self.burger, 1)
        self.client.post(reverse("cart.update", args=[line_key(self.burger.id)]), {"qty": 0})
        self.assertNotIn(line_key(self.burger.id), self.client.session["cart"])

    def test_update_requires_post(self):
        self.add(self.burger, 1)
        response = self.client.get(reverse("cart.update", args=[line_key(self.burger.id)]))
        self.assertEqual(response.status_code, 405)

    def test_cart_page_renders_steppers_with_edge_buttons_disabled(self):
        self.add(self.burger, 1)
        response = self.client.get(reverse("cart.index"))
        self.assertContains(response, reverse("cart.update", args=[line_key(self.burger.id)]))
        self.assertContains(response, 'aria-label="Decrease quantity" disabled')


class CartLegacyShapeTests(CartTestBase):
    def test_legacy_int_shaped_cart_still_counts_and_renders(self):
        session = self.client.session
        session["cart"] = {str(self.burger.id): 2}
        session.save()
        response = self.client.get(reverse("cart.index"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["grand_total"], Decimal("179.98"))
        self.assertContains(response, ">2<")


class CartClearTests(CartTestBase):
    def test_clear_requires_post(self):
        self.add(self.burger, 1)
        response = self.client.get(reverse("cart.clear"))
        self.assertEqual(response.status_code, 405)

    def test_clear_empties_the_cart(self):
        self.add(self.burger, 2)
        self.add(self.wings, 3)
        response = self.client.post(reverse("cart.clear"))
        self.assertRedirects(response, reverse("cart.index"))
        self.assertEqual(self.client.session["cart"], {})


class CartBadgeTests(CartTestBase):
    def test_badge_absent_when_cart_empty(self):
        response = self.client.get(reverse("home.index"))
        self.assertNotContains(response, 'class="cart-badge"')

    def test_badge_shows_summed_quantities_on_every_page(self):
        self.add(self.burger, 2)
        self.add(self.wings, 3)
        for url in (reverse("home.index"), reverse("orders.index"), reverse("cart.index")):
            response = self.client.get(url)
            self.assertContains(response, 'class="cart-badge"')
            self.assertContains(response, ">5<")
