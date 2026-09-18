from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from home.models import TruckLocation
from menu.models import Category, MenuItem, Option, OptionGroup
from orders.models import Order, OrderItem, PickupSlot


class OrderTestBase(TestCase):
    """Two dishes, one customer, one other customer, one staffer."""

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
        cls.customer = User.objects.create_user("thabo", "thabo@example.com", "pw12345678")
        cls.other = User.objects.create_user("zanele", "zanele@example.com", "pw12345678")
        cls.staffer = User.objects.create_user("boss", "boss@example.com", "pw12345678", is_staff=True)

    def fill_cart(self, **items):
        for attr, qty in items.items():
            self.client.post(reverse("cart.add", args=[getattr(self, attr).id]), {"quantity": qty})

    def place_order(self, **items):
        self.fill_cart(**(items or {"burger": 1}))
        return self.client.post(reverse("orders.checkout"), {"customer_name": "Thabo", "phone": "0821234567"})


class CheckoutViewTests(OrderTestBase):
    def test_get_with_items_renders_summary_and_form(self):
        self.fill_cart(burger=2, wings=1)
        response = self.client.get(reverse("orders.checkout"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sizzler Burger")
        self.assertContains(response, "R244.48")
        self.assertContains(response, 'name="customer_name"')

    def test_empty_cart_redirects_to_menu_with_warning(self):
        response = self.client.get(reverse("orders.checkout"))
        self.assertRedirects(response, reverse("home.index"), fetch_redirect_response=False)
        followed = self.client.get(response.url)
        self.assertContains(followed, "Your order is empty")

    def test_empty_cart_post_never_creates_an_order(self):
        response = self.client.post(reverse("orders.checkout"), {"customer_name": "Ghost", "phone": "0821234567"})
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.assertRedirects(response, reverse("home.index"), fetch_redirect_response=False)

    def test_invalid_form_rerenders_and_creates_nothing(self):
        self.fill_cart(burger=1)
        response = self.client.post(reverse("orders.checkout"), {"customer_name": "", "phone": "not-a-phone"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertContains(response, "digits only")
        self.assertEqual(Order.objects.count(), 0)
        self.assertIn("cart", self.client.session)

    def test_successful_checkout_creates_order_with_snapshots(self):
        response = self.place_order(burger=2, wings=1)
        order = Order.objects.get()
        self.assertRedirects(response, reverse("orders.confirmation", args=[order.id]), fetch_redirect_response=False)
        self.assertEqual(order.customer_name, "Thabo")
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.total, Decimal("244.48"))
        lines = order.items.order_by("name_snapshot")
        self.assertEqual(lines.count(), 2)
        self.assertEqual(lines[1].name_snapshot, "Sizzler Burger")
        self.assertEqual(lines[1].price_snapshot, Decimal("89.99"))
        self.assertEqual(lines[1].quantity, 2)

    def test_checkout_clears_the_cart(self):
        self.place_order(burger=1)
        self.assertEqual(self.client.session["cart"], {})

    def test_logged_in_checkout_attaches_the_user(self):
        self.client.force_login(self.customer)
        self.place_order(burger=1)
        self.assertEqual(Order.objects.get().user, self.customer)

    def test_guest_checkout_leaves_user_null(self):
        self.place_order(burger=1)
        order = Order.objects.get()
        self.assertIsNone(order.user)
        self.assertEqual(order.customer_name, "Thabo")

    def test_client_cannot_dictate_the_total(self):
        self.fill_cart(burger=1)
        self.client.post(reverse("orders.checkout"), {
            "customer_name": "Thabo", "phone": "0821234567",
            "total": "0.01", "status": "collected", "user": self.staffer.id,
        })
        order = Order.objects.get()
        self.assertEqual(order.total, Decimal("89.99"))
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertIsNone(order.user)


class OrdersIndexViewTests(OrderTestBase):
    def test_guest_sees_device_orders_and_a_sign_in_banner(self):
        response = self.client.get(reverse("orders.index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Orders from this device")
        self.assertContains(response, "Sign in")
        self.assertEqual(len(response.context["orders"]), 0)

    def test_guest_orders_come_from_the_session(self):
        self.place_order(burger=1)
        order = Order.objects.get()
        response = self.client.get(reverse("orders.index"))
        self.assertContains(response, f"Order #{order.id}")
        self.assertContains(response, "Track")
        self.client.session.flush()
        response = self.client.get(reverse("orders.index"))
        self.assertNotContains(response, f"Order #{order.id}")

    def test_signed_in_user_with_no_orders_sees_empty_state(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("orders.index"))
        self.assertContains(response, "No orders yet")
        self.assertEqual(len(response.context["orders"]), 0)

    def test_lists_only_my_orders_newest_first(self):
        self.client.force_login(self.customer)
        self.place_order(burger=1)
        self.place_order(wings=1)
        Order.objects.create(user=self.other, customer_name="Zanele", phone="0827654321", total=Decimal("10.00"))
        response = self.client.get(reverse("orders.index"))
        orders = list(response.context["orders"])
        self.assertEqual(len(orders), 2)
        self.assertGreater(orders[0].created_at, orders[1].created_at)
        self.assertNotContains(response, "Zanele")

    def test_index_avoids_n_plus_one_queries(self):
        self.client.force_login(self.customer)
        for _ in range(3):
            self.place_order(burger=1, wings=1)
        with self.assertNumQueries(5):
            self.client.get(reverse("orders.index"))


class CheckoutSlotsTipAndGuardTests(OrderTestBase):
    """Phases B and D on checkout: the trading guard, capacity-capped slots,
    the opt-in tip, and the minted collection code."""

    def test_order_gets_a_four_digit_code(self):
        self.place_order(burger=1)
        order = Order.objects.get()
        self.assertRegex(order.code, r"^[1-9]\d{3}$")
        code = order.code
        order.status = Order.Status.PREPARING
        order.save()
        self.assertEqual(order.code, code)

    def test_asap_is_the_default_and_has_no_slot(self):
        self.place_order(burger=1)
        self.assertIsNone(Order.objects.get().slot)

    def test_choosing_a_slot_decrements_its_capacity(self):
        slot = PickupSlot.upcoming(TruckLocation.current())[0]
        self.fill_cart(burger=1)
        response = self.client.post(reverse("orders.checkout"), {"customer_name": "Thabo", "phone": "0821234567", "slot": slot.pk})
        self.assertEqual(response.status_code, 302)
        slot.refresh_from_db()
        self.assertEqual(slot.taken, 1)
        self.assertEqual(Order.objects.get().slot, slot)

    def test_full_slot_is_not_offered_and_not_accepted(self):
        full = PickupSlot.upcoming(TruckLocation.current())[0]
        PickupSlot.objects.filter(pk=full.pk).update(capacity=1, taken=1)
        full.refresh_from_db()
        self.fill_cart(burger=1)
        response = self.client.get(reverse("orders.checkout"))
        self.assertNotIn(full, response.context["slots"])
        response = self.client.post(reverse("orders.checkout"), {"customer_name": "Thabo", "phone": "0821234567", "slot": full.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        full.refresh_from_db()
        self.assertEqual(full.taken, 1)

    def test_tip_is_opt_in_and_adds_ten_rand(self):
        self.fill_cart(burger=1)
        response = self.client.get(reverse("orders.checkout"))
        self.assertNotContains(response, 'name="tip" value="on" data-tip="10.00" checked')
        self.client.post(reverse("orders.checkout"), {"customer_name": "Thabo", "phone": "0821234567", "tip": "on"})
        order = Order.objects.get()
        self.assertEqual(order.tip, Decimal("10.00"))
        self.assertEqual(order.total, Decimal("99.99"))

    def test_closed_truck_shows_the_guard_and_refuses_the_post(self):
        TruckLocation.objects.create(name="Festival", is_live=False)
        session = self.client.session
        session["cart"] = {f"{self.burger.id}:none:0": {"item_id": self.burger.id, "qty": 1, "options": [], "note": ""}}
        session.save()
        response = self.client.get(reverse("orders.checkout"))
        self.assertContains(response, "The grill is off")
        self.assertNotContains(response, 'name="customer_name"')
        self.client.post(reverse("orders.checkout"), {"customer_name": "Thabo", "phone": "0821234567"})
        self.assertEqual(Order.objects.count(), 0)
        self.assertIn(f"{self.burger.id}:none:0", self.client.session["cart"])

    def test_line_snapshots_carry_options_and_the_charged_unit_price(self):
        group = OptionGroup.objects.create(food=self.burger, name="Add Extras", required=False, max_choices=2)
        bacon = Option.objects.create(group=group, name="Bacon bits", price_delta=Decimal("12.00"))
        self.client.post(reverse("cart.add", args=[self.burger.id]), {"quantity": 2, f"group-{group.id}": bacon.id})
        self.client.post(reverse("orders.checkout"), {"customer_name": "Thabo", "phone": "0821234567"})
        line = OrderItem.objects.get()
        self.assertEqual(line.options_snapshot, "Bacon bits")
        self.assertEqual(line.price_snapshot, Decimal("101.99"))
        self.assertEqual(Order.objects.get().total, Decimal("203.98"))


class StaffQueueTests(OrderTestBase):
    """The staff queue: staff-only, one step per POST."""

    def test_non_staff_are_bounced(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("staff.queue"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 0)

    def test_staff_see_todays_live_orders_in_buckets(self):
        self.place_order(burger=1)
        order = Order.objects.get()
        self.client.force_login(self.staffer)
        response = self.client.get(reverse("staff.queue"))
        self.assertContains(response, f"#{order.id}")
        self.assertContains(response, order.code)
        self.assertContains(response, "Start cooking")

    def test_advance_moves_one_step_and_collected_leaves_the_board(self):
        self.place_order(burger=1)
        order = Order.objects.get()
        self.client.force_login(self.staffer)
        for expected in ("preparing", "ready", "collected"):
            response = self.client.post(reverse("staff.advance", args=[order.id]))
            self.assertRedirects(response, reverse("staff.queue"))
            order.refresh_from_db()
            self.assertEqual(order.status, expected)
        response = self.client.get(reverse("staff.queue"))
        self.assertNotContains(response, "Mark collected")
        self.assertContains(response, f"#{order.id} · {order.code}")
        self.client.post(reverse("staff.advance", args=[order.id]))
        order.refresh_from_db()
        self.assertEqual(order.status, "collected")

    def test_advance_requires_post_and_staff(self):
        self.place_order(burger=1)
        order = Order.objects.get()
        self.assertEqual(self.client.post(reverse("staff.advance", args=[order.id])).status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, "pending")
        self.client.force_login(self.staffer)
        self.assertEqual(self.client.get(reverse("staff.advance", args=[order.id])).status_code, 405)


class StatusJsonTests(OrderTestBase):
    """The poll the live status page makes so nobody refreshes."""

    def test_owner_gets_the_status_and_strangers_get_403(self):
        self.place_order(burger=1)
        order = Order.objects.get()
        response = self.client.get(reverse("orders.status_json", args=[order.id]))
        self.assertEqual(response.json(), {"status": "pending"})
        self.client.session.flush()
        self.assertEqual(self.client.get(reverse("orders.status_json", args=[order.id])).status_code, 403)

    def test_status_page_carries_the_rail_and_the_poll_hook(self):
        self.place_order(burger=1)
        order = Order.objects.get()
        response = self.client.get(reverse("orders.show", args=[order.id]))
        self.assertContains(response, "status-step--now")
        self.assertContains(response, reverse("orders.status_json", args=[order.id]))
        self.assertContains(response, order.code)


class OrderDetailViewTests(OrderTestBase):
    def setUp(self):
        self.client.force_login(self.customer)
        self.place_order(burger=2)
        self.order = Order.objects.get()
        self.client.logout()

    def test_owner_can_view(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("orders.show", args=[self.order.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sizzler Burger")
        self.assertContains(response, "R179.98")

    def test_other_user_gets_403(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("orders.show", args=[self.order.id]))
        self.assertEqual(response.status_code, 403)

    def test_staff_can_view_anyones_order(self):
        self.client.force_login(self.staffer)
        response = self.client.get(reverse("orders.show", args=[self.order.id]))
        self.assertEqual(response.status_code, 200)

    def test_anonymous_stranger_gets_403(self):
        response = self.client.get(reverse("orders.show", args=[self.order.id]))
        self.assertEqual(response.status_code, 403)

    def test_unknown_order_is_404(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("orders.show", args=[99999]))
        self.assertEqual(response.status_code, 404)


class ConfirmationViewTests(OrderTestBase):
    def test_guest_who_just_ordered_can_see_their_confirmation(self):
        self.place_order(burger=1)
        order = Order.objects.get()
        response = self.client.get(reverse("orders.confirmation", args=[order.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Got it, Thabo!")

    def test_different_guest_cannot_see_it(self):
        self.place_order(burger=1)
        order = Order.objects.get()
        other_browser = self.client_class()
        response = other_browser.get(reverse("orders.confirmation", args=[order.id]))
        self.assertEqual(response.status_code, 403)

    def test_confirmation_shows_snapshot_lines_and_total(self):
        self.place_order(burger=2, wings=1)
        order = Order.objects.get()
        response = self.client.get(reverse("orders.confirmation", args=[order.id]))
        self.assertContains(response, "2 × Sizzler Burger")
        self.assertContains(response, "R244.48")


class OrderModelTests(OrderTestBase):
    def test_snapshots_survive_menu_price_and_name_changes(self):
        self.place_order(burger=1)
        line = OrderItem.objects.get()
        self.burger.name = "Mega Sizzler"
        self.burger.price = Decimal("129.99")
        self.burger.save()
        line.refresh_from_db()
        self.assertEqual(line.name_snapshot, "Sizzler Burger")
        self.assertEqual(line.price_snapshot, Decimal("89.99"))
        self.assertEqual(line.line_total(), Decimal("89.99"))

    def test_protect_blocks_deleting_a_dish_with_order_history(self):
        self.place_order(burger=1)
        with self.assertRaises(ProtectedError):
            self.burger.delete()
        self.assertTrue(MenuItem.objects.filter(pk=self.burger.pk).exists())

    def test_deleting_an_order_cascades_to_its_lines(self):
        self.place_order(burger=1, wings=1)
        order = Order.objects.get()
        order.delete()
        self.assertEqual(OrderItem.objects.count(), 0)

    def test_deleting_a_user_keeps_their_orders(self):
        self.client.force_login(self.customer)
        self.place_order(burger=1)
        self.customer.delete()
        order = Order.objects.get()
        self.assertIsNone(order.user)
        self.assertEqual(order.customer_name, "Thabo")

    def test_status_choices_expose_human_labels(self):
        order = Order.objects.create(customer_name="X", phone="0821234567", total=Decimal("1.00"))
        self.assertEqual(order.get_status_display(), "Pending")
        order.status = Order.Status.READY
        self.assertEqual(order.get_status_display(), "Ready")


class ReviewEligibilityTests(OrderTestBase):
    """Only a collected order unlocks reviewing."""

    def setUp(self):
        self.client.force_login(self.customer)
        self.url = reverse("menu.review_create", args=[self.burger.slug])
        self.item_url = reverse("menu.show", args=[self.burger.slug])

    def test_user_who_never_ordered_sees_no_form(self):
        response = self.client.get(self.item_url)
        self.assertIsNone(response.context["form"])
        self.assertContains(response, "order it, collect it")

    def test_pending_order_does_not_unlock_reviews(self):
        self.place_order(burger=1)
        response = self.client.get(self.item_url)
        self.assertIsNone(response.context["form"])

    def test_collected_order_unlocks_the_form(self):
        self.place_order(burger=1)
        Order.objects.update(status=Order.Status.COLLECTED)
        response = self.client.get(self.item_url)
        self.assertIsNotNone(response.context["form"])
        self.assertContains(response, "Leave a review")

    def test_posting_a_review_without_a_collected_order_is_refused(self):
        self.place_order(burger=1)
        response = self.client.post(self.url, {"rating": 5, "comment": "Never actually ate this."})
        self.assertEqual(self.burger.reviews.count(), 0)
        self.assertRedirects(response, self.item_url, fetch_redirect_response=False)
        followed = self.client.get(self.item_url)
        self.assertContains(followed, "ordered and collected")

    def test_collected_order_allows_posting(self):
        self.place_order(burger=1)
        Order.objects.update(status=Order.Status.COLLECTED)
        self.client.post(self.url, {"rating": 5, "comment": "Worth the queue."})
        self.assertEqual(self.burger.reviews.count(), 1)

    def test_collecting_one_dish_does_not_unlock_another(self):
        self.place_order(burger=1)
        Order.objects.update(status=Order.Status.COLLECTED)
        response = self.client.get(reverse("menu.show", args=[self.wings.slug]))
        self.assertIsNone(response.context["form"])
