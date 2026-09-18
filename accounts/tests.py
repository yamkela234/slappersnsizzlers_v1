from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User


class SignupViewTests(TestCase):
    """Covers GET rendering plus the success and failure branches of POST."""

    def test_signup_page_renders(self):
        response = self.client.get(reverse("accounts.signup"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/signup.html")

    def test_signup_creates_user_and_logs_them_in(self):
        response = self.client.post(reverse("accounts.signup"), {
            "username": "thandi",
            "email": "thandi@example.com",
            "password1": "sizzler-2026!",
            "password2": "sizzler-2026!",
        })
        self.assertRedirects(response, reverse("home.index") + "#menu")
        self.assertTrue(User.objects.filter(username="thandi", email="thandi@example.com").exists())
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_signup_password_is_hashed_not_plaintext(self):
        self.client.post(reverse("accounts.signup"), {
            "username": "sizzlerfan",
            "email": "fan@example.com",
            "password1": "sizzler-2026!",
            "password2": "sizzler-2026!",
        })
        user = User.objects.get(username="sizzlerfan")
        self.assertNotEqual(user.password, "sizzler-2026!")
        self.assertTrue(user.password.startswith("pbkdf2_"))
        self.assertTrue(user.check_password("sizzler-2026!"))

    def test_signup_rejects_missing_email(self):
        response = self.client.post(reverse("accounts.signup"), {
            "username": "no_email_user",
            "email": "",
            "password1": "sizzler-2026!",
            "password2": "sizzler-2026!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "email", "This field is required.")
        self.assertFalse(User.objects.filter(username="no_email_user").exists())

    def test_signup_rejects_mismatched_passwords(self):
        response = self.client.post(reverse("accounts.signup"), {
            "username": "mismatch",
            "email": "mm@example.com",
            "password1": "sizzler-2026!",
            "password2": "different-2026!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="mismatch").exists())
        self.assertTrue(response.context["form"].errors.get("password2"))

    def test_signup_rejects_duplicate_username(self):
        User.objects.create_user("taken", "taken@example.com", "sizzler-2026!")
        response = self.client.post(reverse("accounts.signup"), {
            "username": "taken",
            "email": "second@example.com",
            "password1": "sizzler-2026!",
            "password2": "sizzler-2026!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(username="taken").count(), 1)


class LoginViewTests(TestCase):
    """Covers GET rendering, both POST branches, and the ?next= redirect."""

    def setUp(self):
        self.user = User.objects.create_user("brandon", "b@example.com", "sizzler-2026!")

    def test_login_page_renders(self):
        response = self.client.get(reverse("accounts.login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")

    def test_login_success_redirects_home(self):
        response = self.client.post(reverse("accounts.login"), {
            "username": "brandon",
            "password": "sizzler-2026!",
        })
        self.assertRedirects(response, reverse("home.index"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_honours_next_parameter(self):
        response = self.client.post(reverse("accounts.login") + "?next=/admin/", {
            "username": "brandon",
            "password": "sizzler-2026!",
        })
        self.assertRedirects(response, "/admin/", fetch_redirect_response=False)

    def test_login_failure_rerenders_with_error(self):
        response = self.client.post(reverse("accounts.login"), {
            "username": "brandon",
            "password": "wrong-password",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertTrue(response.context["form"].non_field_errors())


class LogoutViewTests(TestCase):
    """Covers the POST-only rule and the actual logout behaviour."""

    def setUp(self):
        self.user = User.objects.create_user("zola", "z@example.com", "sizzler-2026!")

    def test_logout_via_post_logs_out_and_redirects(self):
        self.client.login(username="zola", password="sizzler-2026!")
        response = self.client.post(reverse("accounts.logout"))
        self.assertRedirects(response, reverse("home.index"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_via_get_is_rejected(self):
        self.client.login(username="zola", password="sizzler-2026!")
        response = self.client.get(reverse("accounts.logout"))
        self.assertEqual(response.status_code, 405)
        check = self.client.get(reverse("home.index"))
        self.assertTrue(check.wsgi_request.user.is_authenticated)
