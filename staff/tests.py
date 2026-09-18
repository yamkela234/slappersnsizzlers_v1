from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from home.models import TruckLocation
from menu.models import Category, MenuItem, Option, OptionGroup, Review
from orders.models import Order, OrderItem, PickupSlot

FETCH = {"HTTP_X_REQUESTED_WITH": "fetch"}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StaffTestBase(TestCase):
    """A crew member, a manager, a customer; two dishes; one truck row."""

    @classmethod
    def setUpTestData(cls):
        cls.cat = Category.objects.create(name="Wings", slug="wings", sort_order=1)
        cls.wings = MenuItem.objects.create(category=cls.cat, name="Buffalo Wings Combo", slug="wings-combo", price=Decimal("89.99"), is_spicy=True)
        cls.fries = MenuItem.objects.create(category=cls.cat, name="Loaded Fries", slug="fries", price=Decimal("49.99"))
        cls.group = OptionGroup.objects.create(food=cls.wings, name="Choose Sauce", required=True, max_choices=1)
        cls.peri = Option.objects.create(group=cls.group, name="Peri-Peri")
        cls.customer = User.objects.create_user("lerato", "lerato@example.com", "pw", first_name="Lerato", last_name="M")
        cls.crew = User.objects.create_user("sipho", "sipho@example.com", "pw", is_staff=True, first_name="Sipho", last_name="Dlamini")
        cls.manager = User.objects.create_user("thandi", "thandi@example.com", "pw", is_staff=True, first_name="Thandi", last_name="Mokoena")
        cls.manager.groups.add(Group.objects.create(name="Manager"))
        cls.truck = TruckLocation.objects.create(name="Summer Food Festival", zone="4", is_live=True, trading_from=time(0, 0), trading_until=time(0, 0))

    def order(self, status="pending", user=None, **kwargs):
        order = Order.objects.create(customer_name="Lerato M.", phone="0824419920", status=status, total=Decimal("89.99"), user=user, **kwargs)
        OrderItem.objects.create(order=order, menu_item=self.wings, name_snapshot="Buffalo Wings Combo", price_snapshot=Decimal("89.99"), quantity=1, options_snapshot="Peri-Peri")
        return order


class PermissionTests(StaffTestBase):
    CREW_SCREENS = ["staff.dashboard", "staff.queue", "staff.orders", "staff.items"]
    MANAGER_SCREENS = ["staff.options", "staff.reviews", "staff.truck", "staff.slots", "staff.people"]

    def test_anonymous_is_sent_to_login_everywhere(self):
        for name in self.CREW_SCREENS + self.MANAGER_SCREENS:
            self.assertEqual(self.client.get(reverse(name)).status_code, 302, name)

    def test_customers_are_sent_to_login_too(self):
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse("staff.dashboard")).status_code, 302)

    def test_crew_open_their_four_screens_and_get_403_on_the_rest(self):
        self.client.force_login(self.crew)
        for name in self.CREW_SCREENS:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        for name in self.MANAGER_SCREENS:
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_manager_opens_everything(self):
        self.client.force_login(self.manager)
        for name in self.CREW_SCREENS + self.MANAGER_SCREENS:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_superuser_counts_as_owner(self):
        boss = User.objects.create_superuser("boss", "boss@example.com", "pw")
        self.client.force_login(boss)
        response = self.client.get(reverse("staff.people"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Owner")

    def test_crew_nav_hides_manager_screens_but_that_is_not_the_fence(self):
        self.client.force_login(self.crew)
        response = self.client.get(reverse("staff.dashboard"))
        self.assertNotContains(response, reverse("staff.truck"))
        self.assertEqual(self.client.get(reverse("staff.truck")).status_code, 403)

    def test_crew_cannot_reprice_but_can_mark_sold_out(self):
        self.client.force_login(self.crew)
        self.assertEqual(self.client.post(reverse("staff.item_price", args=[self.wings.id]), {"price": "1.00"}).status_code, 403)
        self.wings.refresh_from_db()
        self.assertEqual(self.wings.price, Decimal("89.99"))
        self.client.post(reverse("staff.item_toggle", args=[self.wings.id]))
        self.wings.refresh_from_db()
        self.assertFalse(self.wings.is_available)

    def test_money_is_hidden_from_crew(self):
        self.order()
        self.client.force_login(self.crew)
        response = self.client.get(reverse("staff.dashboard"))
        self.assertContains(response, "Manager access only")
        self.assertNotContains(response, "R89.99")
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(reverse("staff.dashboard")), "R89.99")


class DashboardTests(StaffTestBase):
    def test_tiles_count_todays_orders_and_exclude_cancelled_from_takings(self):
        self.order(); self.order(status="preparing"); self.order(status="cancelled")
        self.client.force_login(self.manager)
        response = self.client.get(reverse("staff.dashboard"))
        self.assertContains(response, "2 still live")
        self.assertContains(response, "R179.98")
        self.assertContains(response, "0 waiting at the hatch")

    def test_needs_attention_lists_sold_out_dishes_and_low_star_reviews(self):
        self.fries.is_available = False
        self.fries.save()
        Review.objects.create(menu_item=self.wings, user=self.customer, rating=1, comment="Visit cheap-wings-dot-biz!!!")
        self.client.force_login(self.manager)
        response = self.client.get(reverse("staff.dashboard"))
        self.assertContains(response, "Loaded Fries is off the menu")
        self.assertContains(response, "1 low-star review to look at")

    def test_quiet_day_says_so(self):
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(reverse("staff.dashboard")), "Nothing needs you right now.")

    def test_avg_prep_is_measured_from_the_stamps(self):
        order = self.order(status="ready")
        order.preparing_at = timezone.now() - timedelta(minutes=11)
        order.ready_at = timezone.now()
        order.save()
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(reverse("staff.dashboard")), "11 min")


class QueueTests(StaffTestBase):
    def test_buckets_show_live_orders_and_collected_leaves_the_board(self):
        live = self.order()
        done = self.order(status="collected")
        self.client.force_login(self.crew)
        response = self.client.get(reverse("staff.queue"))
        self.assertContains(response, f"#{live.id}")
        self.assertContains(response, "Start cooking")
        self.assertContains(response, f"#{done.id} · {done.code}")

    def test_advance_moves_one_step_and_stamps_the_clock(self):
        order = self.order()
        self.client.force_login(self.crew)
        for expected in ("preparing", "ready", "collected"):
            response = self.client.post(reverse("staff.advance", args=[order.id]))
            self.assertRedirects(response, reverse("staff.queue"), fetch_redirect_response=False)
            order.refresh_from_db()
            self.assertEqual(order.status, expected)
        self.assertIsNotNone(order.preparing_at)
        self.assertIsNotNone(order.ready_at)
        self.assertGreaterEqual(order.ready_at, order.preparing_at)
        self.client.post(reverse("staff.advance", args=[order.id]))
        order.refresh_from_db()
        self.assertEqual(order.status, "collected")

    def test_advance_as_fetch_returns_json_with_the_regions_to_swap(self):
        order = self.order()
        self.client.force_login(self.crew)
        response = self.client.post(reverse("staff.advance", args=[order.id]), **FETCH)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], f"#{order.id} → Preparing")
        self.assertIn("#queue-board", data["updates"])
        self.assertIn("Mark ready", data["updates"]["#queue-board"])
        self.assertIn('id="nav-badge-live"', data["updates"]["#nav-badge-live"])

    def test_advance_requires_post(self):
        order = self.order()
        self.client.force_login(self.crew)
        self.assertEqual(self.client.get(reverse("staff.advance", args=[order.id])).status_code, 405)

    def test_advance_honours_a_safe_next_and_ignores_an_offsite_one(self):
        order = self.order()
        self.client.force_login(self.crew)
        response = self.client.post(reverse("staff.advance", args=[order.id]), {"next": reverse("staff.dashboard")})
        self.assertRedirects(response, reverse("staff.dashboard"), fetch_redirect_response=False)
        response = self.client.post(reverse("staff.advance", args=[order.id]), {"next": "https://evil.example/"})
        self.assertRedirects(response, reverse("staff.queue"), fetch_redirect_response=False)

    def test_queue_partial_is_just_the_board(self):
        self.client.force_login(self.crew)
        response = self.client.get(reverse("staff.queue_partial"))
        self.assertContains(response, 'id="queue-board"')
        self.assertNotContains(response, "<html")


class OrdersTests(StaffTestBase):
    def test_filters_and_search_compose(self):
        a = self.order()
        b = self.order(status="collected")
        b.customer_name, b.phone = "Devon S.", "0712204417"
        b.save()
        self.client.force_login(self.crew)
        response = self.client.get(reverse("staff.orders") + "?status=collected")
        self.assertContains(response, f"order-row-{b.id}")
        self.assertNotContains(response, f"order-row-{a.id}")
        response = self.client.get(reverse("staff.orders") + "?q=0712")
        self.assertContains(response, f"order-row-{b.id}")
        self.assertNotContains(response, f"order-row-{a.id}")
        response = self.client.get(reverse("staff.orders") + "?q=nobody")
        self.assertContains(response, "No orders match that filter.")

    def test_drawer_is_json_for_fetch_and_a_full_page_otherwise(self):
        order = self.order()
        self.client.force_login(self.crew)
        response = self.client.get(reverse("staff.order", args=[order.id]), **FETCH)
        self.assertIn(order.code, response.json()["html"])
        response = self.client.get(reverse("staff.order", args=[order.id]))
        self.assertContains(response, 'role="dialog"')
        self.assertContains(response, "Total to pay at the stall")


class ItemTests(StaffTestBase):
    def test_price_commits_and_rejects_junk(self):
        self.client.force_login(self.manager)
        self.client.post(reverse("staff.item_price", args=[self.wings.id]), {"price": "95"})
        self.wings.refresh_from_db()
        self.assertEqual(self.wings.price, Decimal("95.00"))
        response = self.client.post(reverse("staff.item_price", args=[self.wings.id]), {"price": "-5"}, **FETCH)
        self.assertEqual(response.status_code, 400)
        self.wings.refresh_from_db()
        self.assertEqual(self.wings.price, Decimal("95.00"))
        self.assertIn(f'id="item-row-{self.wings.id}"', response.json()["updates"][f"#item-row-{self.wings.id}"])

    def test_toggle_flips_availability_and_answers_with_the_row(self):
        self.client.force_login(self.crew)
        response = self.client.post(reverse("staff.item_toggle", args=[self.wings.id]), **FETCH)
        self.wings.refresh_from_db()
        self.assertFalse(self.wings.is_available)
        self.assertEqual(response.json()["message"], "Buffalo Wings Combo marked sold out")
        self.assertIn('aria-checked="false"', response.json()["updates"][f"#item-row-{self.wings.id}"])

    def test_drawer_saves_the_record_and_never_touches_the_slug(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("staff.item_edit", args=[self.wings.id]), {
            "name": "Buffalo Wings", "description": "Eight wings.", "price": "92.50", "prep_minutes": "14",
            "category": self.cat.id, "is_spicy": "on", "slug": "hacked",
        }, **FETCH)
        self.assertEqual(response.status_code, 200)
        self.wings.refresh_from_db()
        self.assertEqual((self.wings.name, self.wings.price, self.wings.prep_minutes, self.wings.slug), ("Buffalo Wings", Decimal("92.50"), 14, "wings-combo"))
        self.assertFalse(self.wings.is_available)
        self.assertEqual(response.json()["updates"]["#drawer-root"], "")

    def test_drawer_rerenders_with_errors(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("staff.item_edit", args=[self.wings.id]), {"name": "", "price": "x", "prep_minutes": "1", "category": self.cat.id}, **FETCH)
        self.assertEqual(response.status_code, 400)
        self.assertIn("has-error", response.json()["html"])


class OptionTests(StaffTestBase):
    def test_group_fields_each_write_alone(self):
        self.client.force_login(self.manager)
        self.client.post(reverse("staff.group_update", args=[self.group.id]), {"required": "0"})
        self.client.post(reverse("staff.group_update", args=[self.group.id]), {"max_choices": "9"})
        self.client.post(reverse("staff.group_update", args=[self.group.id]), {"name": "Pick a sauce"})
        self.group.refresh_from_db()
        self.assertEqual((self.group.required, self.group.max_choices, self.group.name), (False, 6, "Pick a sauce"))

    def test_option_add_update_delete(self):
        self.client.force_login(self.manager)
        self.client.post(reverse("staff.option_add", args=[self.group.id]))
        new = self.group.options.get(name="New option")
        self.client.post(reverse("staff.option_update", args=[new.id]), {"name": "Bacon bits"})
        self.client.post(reverse("staff.option_update", args=[new.id]), {"price_delta": "12"})
        self.client.post(reverse("staff.option_update", args=[new.id]), {"toggle": "1"})
        new.refresh_from_db()
        self.assertEqual((new.name, new.price_delta, new.is_available), ("Bacon bits", Decimal("12.00"), False))
        self.client.post(reverse("staff.option_delete", args=[new.id]))
        self.assertFalse(Option.objects.filter(pk=new.id).exists())

    def test_deleting_a_group_leaves_past_orders_alone(self):
        order = self.order()
        self.client.force_login(self.manager)
        response = self.client.post(reverse("staff.group_delete", args=[self.group.id]), **FETCH)
        self.assertEqual(response.json()["updates"][f"#group-{self.group.id}"], "")
        self.assertFalse(OptionGroup.objects.filter(pk=self.group.id).exists())
        self.assertEqual(order.items.get().options_snapshot, "Peri-Peri")

    def test_options_page_picks_the_dish_from_the_querystring(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("staff.options") + "?food=fries")
        self.assertContains(response, "Loaded Fries asks nothing")
        self.client.post(reverse("staff.group_add", args=[self.fries.id]))
        self.assertEqual(self.fries.option_groups.count(), 1)


class ReviewTests(StaffTestBase):
    def setUp(self):
        self.review = Review.objects.create(menu_item=self.wings, user=self.customer, rating=1, comment="Visit cheap-wings-dot-biz!!!")
        self.good = Review.objects.create(menu_item=self.wings, user=self.crew, rating=5, comment="Best wings.")

    def test_hide_removes_it_from_the_dish_page_and_the_average(self):
        self.assertEqual(self.wings.average_rating(), 3)
        self.client.force_login(self.manager)
        response = self.client.post(reverse("staff.review_hide", args=[self.review.id]), **FETCH)
        self.assertEqual(response.json()["message"], "Review hidden from the dish page")
        self.assertIn("is-hidden", response.json()["updates"][f"#review-{self.review.id}"])
        self.assertEqual(self.wings.average_rating(), 5)
        self.assertEqual(self.wings.review_count(), 1)
        page = self.client.get(self.wings.get_absolute_url())
        self.assertNotContains(page, "cheap-wings")
        self.assertContains(page, "Best wings.")

    def test_hidden_filter_and_badge(self):
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(reverse("staff.reviews")), 'id="nav-badge-flagged"')
        self.client.post(reverse("staff.review_hide", args=[self.review.id]))
        response = self.client.get(reverse("staff.reviews") + "?rating=hidden")
        self.assertContains(response, "cheap-wings")
        self.assertNotContains(response, "Best wings.")
        self.assertContains(response, 'id="nav-badge-flagged" class="adm-nav-badge" hidden')

    def test_delete(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("staff.review_delete", args=[self.review.id]), **FETCH)
        self.assertEqual(response.json()["updates"][f"#review-{self.review.id}"], "")
        self.assertFalse(Review.objects.filter(pk=self.review.id).exists())

    def test_author_of_a_hidden_review_still_sees_it_as_theirs(self):
        self.review.is_hidden = True
        self.review.save()
        self.client.force_login(self.customer)
        page = self.client.get(self.wings.get_absolute_url())
        self.assertNotContains(page, 'name="rating"')


class TruckTests(StaffTestBase):
    def test_form_saves_the_row(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("staff.truck"), {
            "name": "V&A Market", "zone": "B2", "trading_from": "11:00", "trading_until": "22:00", "ready_minutes": "12", "slot_capacity": "6",
        })
        self.assertRedirects(response, reverse("staff.truck"), fetch_redirect_response=False)
        self.truck.refresh_from_db()
        self.assertEqual((self.truck.name, self.truck.zone, self.truck.ready_minutes, self.truck.slot_capacity), ("V&A Market", "B2", 12, 6))
        self.assertTrue(self.truck.is_live)

    def test_live_switch_flips_the_storefront(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("staff.truck_live"), **FETCH)
        self.truck.refresh_from_db()
        self.assertFalse(self.truck.is_live)
        self.assertIn("Not trading", response.json()["updates"]["#header-trading"])
        self.assertIn("context-bar--closed", response.json()["updates"]["#truck-preview"])
        self.assertContains(self.client.get(reverse("home.index")), "Not trading right now")

    def test_preview_uses_the_real_context_bar_classes(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("staff.truck"))
        self.assertContains(response, "context-bar adm-preview-bar")
        self.assertContains(response, "Summer Food Festival · Zone 4")


class SlotTests(StaffTestBase):
    def slot(self, capacity=8, taken=0, minutes=30):
        start = (timezone.now() + timedelta(minutes=minutes)).replace(second=0, microsecond=0)
        return PickupSlot.objects.create(start=start, capacity=capacity, taken=taken)

    def test_capacity_floor_is_taken(self):
        slot = self.slot(capacity=4, taken=4)
        self.client.force_login(self.manager)
        response = self.client.post(reverse("staff.slot_capacity", args=[slot.id]), {"delta": "-1"}, **FETCH)
        slot.refresh_from_db()
        self.assertEqual(slot.capacity, 4)
        self.assertIn("Full — off checkout", response.json()["updates"][f"#slot-{slot.id}"])
        self.client.post(reverse("staff.slot_capacity", args=[slot.id]), {"delta": "1"})
        slot.refresh_from_db()
        self.assertEqual(slot.capacity, 5)

    def test_close_deletes_an_empty_window_but_caps_a_booked_one(self):
        empty, booked = self.slot(), self.slot(capacity=8, taken=3, minutes=45)
        self.client.force_login(self.manager)
        self.client.post(reverse("staff.slot_close", args=[empty.id]))
        self.assertFalse(PickupSlot.objects.filter(pk=empty.id).exists())
        self.client.post(reverse("staff.slot_close", args=[booked.id]))
        booked.refresh_from_db()
        self.assertEqual(booked.capacity, 3)
        self.assertEqual(booked.remaining, 0)

    def test_add_appends_a_window_at_the_trucks_capacity(self):
        self.client.force_login(self.manager)
        self.client.post(reverse("staff.slot_add"))
        before = PickupSlot.objects.count()
        response = self.client.post(reverse("staff.slot_add"), **FETCH)
        self.assertEqual(PickupSlot.objects.count(), before + 1)
        self.assertEqual(PickupSlot.objects.order_by("-start").first().capacity, self.truck.slot_capacity)
        self.assertIn('id="slots-list"', response.json()["updates"]["#slots-list"])

    def test_full_windows_are_listed_for_staff_but_not_for_customers(self):
        full = self.slot(capacity=2, taken=2)
        self.client.force_login(self.manager)
        self.assertContains(self.client.get(reverse("staff.slots")), full.label())
        self.assertNotIn(full, PickupSlot.upcoming(self.truck))


class PeopleTests(StaffTestBase):
    def test_list_shows_staff_with_roles(self):
        self.client.force_login(self.manager)
        response = self.client.get(reverse("staff.people"))
        self.assertContains(response, "Sipho Dlamini")
        self.assertContains(response, "Crew")
        self.assertContains(response, "Manager")
        self.assertNotContains(response, "lerato@example.com")

    def test_suspend_and_restore_but_never_yourself(self):
        self.client.force_login(self.manager)
        self.client.post(reverse("staff.person_toggle", args=[self.crew.id]))
        self.crew.refresh_from_db()
        self.assertFalse(self.crew.is_active)
        self.client.post(reverse("staff.person_toggle", args=[self.crew.id]))
        self.crew.refresh_from_db()
        self.assertTrue(self.crew.is_active)
        response = self.client.post(reverse("staff.person_toggle", args=[self.manager.id]), **FETCH)
        self.assertEqual(response.status_code, 400)
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)

    def test_invite_creates_a_staff_account_in_the_group(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("staff.invite"), {"name": "Mika Venter", "email": "mika@slappers.co.za", "role": "Manager"}, **FETCH)
        self.assertEqual(response.json()["message"], "Mika Venter added as Manager")
        mika = User.objects.get(email="mika@slappers.co.za")
        self.assertTrue(mika.is_staff)
        self.assertFalse(mika.has_usable_password())
        self.assertEqual((mika.username, mika.first_name, mika.last_name), ("mika", "Mika", "Venter"))
        self.assertTrue(mika.groups.filter(name="Manager").exists())
        self.assertIn("Mika Venter", response.json()["updates"]["#people-list"])

    def test_invite_refuses_an_empty_name_and_a_duplicate_email(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("staff.invite"), {"name": "", "email": "new@slappers.co.za", "role": "Crew"}, **FETCH)
        self.assertEqual(response.json()["message"], "Give them a name first")
        response = self.client.post(reverse("staff.invite"), {"name": "Again", "email": "sipho@example.com", "role": "Crew"}, **FETCH)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(User.objects.filter(is_staff=True).count(), 2)
