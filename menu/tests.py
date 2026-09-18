import tempfile
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse

from orders.models import Order, OrderItem

from home.models import TruckLocation

from .models import Category, MenuItem, Option, OptionGroup, Review


def make_menu():
    """Shared fixture: one category and two items. A plain function (not setUp)
    so both view and model test classes can call it without inheritance tricks."""
    category = Category.objects.create(name="Burgers", slug="burgers", sort_order=1)
    burger = MenuItem.objects.create(category=category, name="Sizzler Burger", slug="sizzler-burger", description="Double patty, bacon", price="79.99")
    fries = MenuItem.objects.create(category=category, name="Loaded Fries", slug="loaded-fries", description="Cheese sauce", price="49.99")
    return burger, fries


def give_collected_order(user, *items):
    """Give `user` a collected order containing `items` so they can review them."""
    order = Order.objects.create(
        user=user,
        customer_name=user.username,
        phone="0821234567",
        status=Order.Status.COLLECTED,
        total="0.00",
    )
    for item in items:
        OrderItem.objects.create(
            order=order, menu_item=item,
            name_snapshot=item.name, price_snapshot=item.price, quantity=1,
        )
    return order


class MenuIndexViewTests(TestCase):
    """The menu lives on the home page now (the truck has five items); /menu/
    only redirects there so old links and the signup redirect still land."""

    def setUp(self):
        self.burger, self.fries = make_menu()

    def test_menu_index_redirects_to_the_home_menu_section(self):
        response = self.client.get(reverse("menu.index"))
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], reverse("home.index") + "#menu")

    def test_home_renders_all_available_items(self):
        response = self.client.get(reverse("home.index"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home/index.html")
        self.assertContains(response, 'id="menu"')
        self.assertContains(response, "Sizzler Burger")
        self.assertContains(response, "Loaded Fries")

    def test_home_hides_unavailable_items(self):
        self.fries.is_available = False
        self.fries.save()
        response = self.client.get(reverse("home.index"))
        self.assertContains(response, "Sizzler Burger")
        self.assertNotContains(response, "Loaded Fries")

    def test_grid_add_is_a_post_or_a_modal_trigger(self):
        OptionGroup.objects.create(food=self.burger, name="Choose Sauce", required=True)
        response = self.client.get(reverse("home.index"))
        self.assertContains(response, f'data-modal="customise-{self.burger.id}"')
        self.assertContains(response, f'id="customise-{self.burger.id}"')
        self.assertContains(response, reverse("cart.add", args=[self.fries.id]))
        self.assertNotContains(response, f'id="customise-{self.fries.id}"')

    def test_closed_truck_disables_every_add(self):
        TruckLocation.objects.create(name="Festival", is_live=False)
        response = self.client.get(reverse("home.index"))
        self.assertContains(response, "Not trading right now")
        self.assertContains(response, ">Closed<")
        self.assertNotContains(response, reverse("cart.add", args=[self.fries.id]))


class MenuShowViewTests(TestCase):
    """The /menu/<slug>/ detail page: rating summary, review list, and which
    review UI each kind of visitor sees."""

    def setUp(self):
        self.burger, self.fries = make_menu()
        self.alice = User.objects.create_user("alice", "a@example.com", "sizzler-2026!")
        self.bob = User.objects.create_user("bob", "b@example.com", "sizzler-2026!")

    def test_show_renders_item(self):
        response = self.client.get(reverse("menu.show", args=["sizzler-burger"]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "menu/show.html")
        self.assertContains(response, "Sizzler Burger")
        self.assertContains(response, "No ratings yet")

    def test_show_unknown_slug_is_404(self):
        response = self.client.get(reverse("menu.show", args=["does-not-exist"]))
        self.assertEqual(response.status_code, 404)

    def test_show_displays_average_and_count(self):
        Review.objects.create(menu_item=self.burger, user=self.alice, rating=5, comment="Great")
        Review.objects.create(menu_item=self.burger, user=self.bob, rating=4, comment="Good")
        response = self.client.get(reverse("menu.show", args=["sizzler-burger"]))
        self.assertEqual(response.context["average_rating"], 4.5)
        self.assertEqual(response.context["review_count"], 2)
        self.assertContains(response, "4.5")
        self.assertContains(response, "2 reviews")

    def test_show_lists_reviews_newest_first(self):
        older = Review.objects.create(menu_item=self.burger, user=self.alice, rating=3, comment="First review")
        newer = Review.objects.create(menu_item=self.burger, user=self.bob, rating=5, comment="Second review")
        response = self.client.get(reverse("menu.show", args=["sizzler-burger"]))
        self.assertEqual(list(response.context["reviews"]), [newer, older])

    def test_anonymous_sees_login_prompt_not_form(self):
        response = self.client.get(reverse("menu.show", args=["sizzler-burger"]))
        self.assertIsNone(response.context["form"])
        self.assertContains(response, "to leave a review")
        self.assertContains(response, "?next=/menu/sizzler-burger/")

    def test_logged_in_user_without_review_sees_form(self):
        give_collected_order(self.alice, self.burger)
        self.client.login(username="alice", password="sizzler-2026!")
        response = self.client.get(reverse("menu.show", args=["sizzler-burger"]))
        self.assertIsNotNone(response.context["form"])
        self.assertIsNone(response.context["user_review"])
        self.assertContains(response, "Leave a review")
        self.assertContains(response, reverse("menu.review_create", args=["sizzler-burger"]))

    def test_logged_in_user_with_review_sees_edit_delete_not_form(self):
        review = Review.objects.create(menu_item=self.burger, user=self.alice, rating=4, comment="Mine")
        self.client.login(username="alice", password="sizzler-2026!")
        response = self.client.get(reverse("menu.show", args=["sizzler-burger"]))
        self.assertEqual(response.context["user_review"], review)
        self.assertIsNone(response.context["form"])
        self.assertContains(response, reverse("menu.review_edit", args=["sizzler-burger", review.id]))
        self.assertContains(response, reverse("menu.review_delete", args=["sizzler-burger", review.id]))
        self.assertNotContains(response, "Leave a review")


class MenuShowOptionGroupTests(TestCase):
    """Option groups on the dish page."""

    def setUp(self):
        self.burger, self.fries = make_menu()
        self.sauces = OptionGroup.objects.create(food=self.burger, name="Choose Sauce", required=True, max_choices=1, sort_order=1)
        self.peri = Option.objects.create(group=self.sauces, name="Peri-Peri")
        self.extras = OptionGroup.objects.create(food=self.burger, name="Add Extras", required=False, max_choices=3, sort_order=2)
        self.bacon = Option.objects.create(group=self.extras, name="Bacon bits", price_delta="12.00")

    def test_groups_render_with_the_right_badges(self):
        response = self.client.get(self.burger.get_absolute_url())
        self.assertContains(response, "Choose Sauce")
        self.assertContains(response, "option-badge--required")
        self.assertContains(response, "option-badge--free")
        self.assertContains(response, "+R12.00")
        self.assertContains(response, f'name="group-{self.sauces.id}"')
        self.assertContains(response, 'type="checkbox"')

    def test_dish_without_groups_has_no_picker(self):
        response = self.client.get(self.fries.get_absolute_url())
        self.assertNotContains(response, 'name="group-')

    def test_sold_out_option_is_not_offered(self):
        Option.objects.create(group=self.sauces, name="Mystery", is_available=False)
        response = self.client.get(self.burger.get_absolute_url())
        self.assertNotContains(response, "Mystery")

    def test_cart_link_restores_a_lines_choices(self):
        response = self.client.get(self.burger.get_absolute_url() + f"?opt={self.bacon.id}&qty=3")
        self.assertEqual(response.context["selected_ids"], {self.bacon.id})
        self.assertEqual(response.context["initial_qty"], 3)
        self.assertContains(response, f'value="{self.bacon.id}" data-delta="12.00"\n                   checked')

    def test_closed_truck_replaces_the_add_button(self):
        TruckLocation.objects.create(name="Festival", is_live=False)
        response = self.client.get(self.burger.get_absolute_url())
        self.assertContains(response, "Closed right now")
        self.assertNotContains(response, "add-to-cart-btn")


class ReviewCreateViewTests(TestCase):
    """POST /menu/<slug>/review/create/."""

    def setUp(self):
        self.burger, self.fries = make_menu()
        self.alice = User.objects.create_user("alice", "a@example.com", "sizzler-2026!")
        self.bob = User.objects.create_user("bob", "b@example.com", "sizzler-2026!")
        give_collected_order(self.alice, self.burger, self.fries)
        give_collected_order(self.bob, self.burger)
        self.url = reverse("menu.review_create", args=["sizzler-burger"])

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.post(self.url, {"rating": 5, "comment": "Yum"})
        self.assertRedirects(response, f"{reverse('accounts.login')}?next={self.url}")
        self.assertEqual(Review.objects.count(), 0)

    def test_valid_post_creates_review_owned_by_request_user(self):
        self.client.login(username="alice", password="sizzler-2026!")
        response = self.client.post(self.url, {
            "rating": 5,
            "comment": "Best burger in Cape Town",
            "user": self.bob.id,
        })
        self.assertRedirects(response, reverse("menu.show", args=["sizzler-burger"]))
        review = Review.objects.get()
        self.assertEqual(review.user, self.alice)
        self.assertEqual(review.menu_item, self.burger)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.comment, "Best burger in Cape Town")

    def test_invalid_rating_rerenders_with_errors(self):
        self.client.login(username="alice", password="sizzler-2026!")
        response = self.client.post(self.url, {"rating": 9, "comment": "Off the scale"})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "menu/show.html")
        self.assertTrue(response.context["form"].errors.get("rating"))
        self.assertEqual(Review.objects.count(), 0)

    def test_missing_comment_rerenders_with_errors(self):
        self.client.login(username="alice", password="sizzler-2026!")
        response = self.client.post(self.url, {"rating": 4, "comment": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "comment", "This field is required.")
        self.assertEqual(Review.objects.count(), 0)

    def test_second_review_for_same_item_is_refused(self):
        Review.objects.create(menu_item=self.burger, user=self.alice, rating=3, comment="Already said my piece")
        self.client.login(username="alice", password="sizzler-2026!")
        response = self.client.post(self.url, {"rating": 5, "comment": "Trying again"})
        self.assertRedirects(response, reverse("menu.show", args=["sizzler-burger"]))
        self.assertEqual(Review.objects.filter(user=self.alice, menu_item=self.burger).count(), 1)
        self.assertEqual(Review.objects.get().comment, "Already said my piece")

    def test_same_user_can_review_a_different_item(self):
        Review.objects.create(menu_item=self.burger, user=self.alice, rating=3, comment="Burger review")
        self.client.login(username="alice", password="sizzler-2026!")
        response = self.client.post(reverse("menu.review_create", args=["loaded-fries"]), {"rating": 5, "comment": "Fries review"})
        self.assertRedirects(response, reverse("menu.show", args=["loaded-fries"]))
        self.assertEqual(Review.objects.filter(user=self.alice).count(), 2)

    def test_get_redirects_back_to_item(self):
        self.client.login(username="alice", password="sizzler-2026!")
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("menu.show", args=["sizzler-burger"]))

    def test_unknown_slug_is_404(self):
        self.client.login(username="alice", password="sizzler-2026!")
        response = self.client.post(reverse("menu.review_create", args=["nope"]), {"rating": 5, "comment": "?"})
        self.assertEqual(response.status_code, 404)


class ReviewEditViewTests(TestCase):
    """GET/POST /menu/<slug>/review/<id>/edit/."""

    def setUp(self):
        self.burger, self.fries = make_menu()
        self.alice = User.objects.create_user("alice", "a@example.com", "sizzler-2026!")
        self.bob = User.objects.create_user("bob", "b@example.com", "sizzler-2026!")
        self.review = Review.objects.create(menu_item=self.burger, user=self.alice, rating=3, comment="Decent")
        self.url = reverse("menu.review_edit", args=["sizzler-burger", self.review.id])

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('accounts.login')}?next={self.url}")

    def test_owner_sees_prefilled_form(self):
        self.client.login(username="alice", password="sizzler-2026!")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "menu/review_form.html")
        self.assertEqual(response.context["form"].instance, self.review)
        self.assertContains(response, "Decent")

    def test_owner_can_update(self):
        self.client.login(username="alice", password="sizzler-2026!")
        response = self.client.post(self.url, {"rating": 5, "comment": "Changed my mind — superb"})
        self.assertRedirects(response, reverse("menu.show", args=["sizzler-burger"]))
        self.review.refresh_from_db()
        self.assertEqual(self.review.rating, 5)
        self.assertEqual(self.review.comment, "Changed my mind — superb")
        self.assertEqual(Review.objects.count(), 1)

    def test_other_user_gets_403(self):
        self.client.login(username="bob", password="sizzler-2026!")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
        response = self.client.post(self.url, {"rating": 1, "comment": "Hijacked"})
        self.assertEqual(response.status_code, 403)
        self.review.refresh_from_db()
        self.assertEqual(self.review.comment, "Decent")

    def test_mismatched_slug_is_404(self):
        self.client.login(username="alice", password="sizzler-2026!")
        wrong_url = reverse("menu.review_edit", args=["loaded-fries", self.review.id])
        response = self.client.get(wrong_url)
        self.assertEqual(response.status_code, 404)

    def test_invalid_post_rerenders_form(self):
        self.client.login(username="alice", password="sizzler-2026!")
        response = self.client.post(self.url, {"rating": 0, "comment": "Zero"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("rating"))
        self.review.refresh_from_db()
        self.assertEqual(self.review.rating, 3)


class ReviewDeleteViewTests(TestCase):
    """GET shows a confirmation; only POST deletes; only the owner may do either."""

    def setUp(self):
        self.burger, self.fries = make_menu()
        self.alice = User.objects.create_user("alice", "a@example.com", "sizzler-2026!")
        self.bob = User.objects.create_user("bob", "b@example.com", "sizzler-2026!")
        self.review = Review.objects.create(menu_item=self.burger, user=self.alice, rating=2, comment="Meh")
        self.url = reverse("menu.review_delete", args=["sizzler-burger", self.review.id])

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.post(self.url)
        self.assertRedirects(response, f"{reverse('accounts.login')}?next={self.url}")
        self.assertEqual(Review.objects.count(), 1)

    def test_get_shows_confirmation_and_does_not_delete(self):
        self.client.login(username="alice", password="sizzler-2026!")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "menu/review_confirm_delete.html")
        self.assertContains(response, "Delete this review?")
        self.assertEqual(Review.objects.count(), 1)

    def test_owner_post_deletes_and_redirects(self):
        self.client.login(username="alice", password="sizzler-2026!")
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse("menu.show", args=["sizzler-burger"]))
        self.assertEqual(Review.objects.count(), 0)

    def test_other_user_gets_403_on_get_and_post(self):
        self.client.login(username="bob", password="sizzler-2026!")
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.assertEqual(Review.objects.count(), 1)

    def test_mismatched_slug_is_404(self):
        self.client.login(username="alice", password="sizzler-2026!")
        wrong_url = reverse("menu.review_delete", args=["loaded-fries", self.review.id])
        self.assertEqual(self.client.post(wrong_url).status_code, 404)
        self.assertEqual(Review.objects.count(), 1)


class MenuModelTests(TestCase):
    """Model-level behaviour that the views rely on."""

    def setUp(self):
        self.burger, self.fries = make_menu()
        self.alice = User.objects.create_user("alice", "a@example.com", "sizzler-2026!")
        self.bob = User.objects.create_user("bob", "b@example.com", "sizzler-2026!")

    def test_average_rating_is_none_without_reviews(self):
        self.assertIsNone(self.burger.average_rating())
        self.assertEqual(self.burger.review_count(), 0)

    def test_average_rating_uses_only_this_items_reviews(self):
        Review.objects.create(menu_item=self.burger, user=self.alice, rating=2, comment="a")
        Review.objects.create(menu_item=self.burger, user=self.bob, rating=4, comment="b")
        Review.objects.create(menu_item=self.fries, user=self.alice, rating=5, comment="c")
        self.assertEqual(self.burger.average_rating(), 3.0)
        self.assertEqual(self.burger.review_count(), 2)
        self.assertEqual(self.fries.average_rating(), 5.0)

    def test_unique_together_blocks_duplicate_review_at_db_level(self):
        Review.objects.create(menu_item=self.burger, user=self.alice, rating=5, comment="first")
        with self.assertRaises(IntegrityError):
            Review.objects.create(menu_item=self.burger, user=self.alice, rating=1, comment="second")

    def test_related_name_reverse_accessors(self):
        review = Review.objects.create(menu_item=self.burger, user=self.alice, rating=5, comment="x")
        self.assertIn(review, self.burger.reviews.all())
        self.assertIn(review, self.alice.reviews.all())
        self.assertIn(self.burger, self.burger.category.items.all())

    def test_get_absolute_url_and_str(self):
        self.assertEqual(self.burger.get_absolute_url(), "/menu/sizzler-burger/")
        review = Review.objects.create(menu_item=self.burger, user=self.alice, rating=4, comment="x")
        self.assertEqual(str(review), "alice on Sizzler Burger: 4/5")


class SeedMenuCommandTests(TestCase):
    """seed_menu, including re-attaching images after a media wipe."""

    def test_reattaches_photo_when_the_file_is_gone_but_the_path_remains(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                call_command("seed_menu", stdout=StringIO())
                item = MenuItem.objects.exclude(image="").first()
                self.assertIsNotNone(item, "seed_menu should attach at least one bundled photo")
                stored_name = item.image.name

                item.image.storage.delete(stored_name)
                self.assertFalse(item.image.storage.exists(stored_name))
                item.refresh_from_db()
                self.assertTrue(item.image)

                call_command("seed_menu", stdout=StringIO())
                item.refresh_from_db()
                self.assertTrue(item.image.storage.exists(item.image.name))

    def test_is_idempotent(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                call_command("seed_menu", stdout=StringIO())
                first_count = MenuItem.objects.count()
                call_command("seed_menu", stdout=StringIO())
                self.assertEqual(MenuItem.objects.count(), first_count)
