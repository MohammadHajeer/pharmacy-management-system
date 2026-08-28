from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]
)
class LoginViewTests(TestCase):
    def setUp(self):
        self.login_url = reverse("accounts:login")
        self.user = get_user_model().objects.create_user(
            username="pharmacist",
            password="test-password",
        )

    def test_login_page_manually_renders_authentication_form_fields(self):
        response = self.client.get(self.login_url)

        self.assertContains(response, 'href="/static/logo-icon.png"')
        self.assertContains(response, 'src="/static/logo.png"')
        self.assertNotContains(response, "favicon.svg")
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'id="id_username"')
        self.assertContains(response, 'autocomplete="username"')
        self.assertContains(response, 'name="password"')
        self.assertContains(response, 'type="password"')
        self.assertContains(response, 'autocomplete="current-password"')
        self.assertContains(response, "data-submit-form")
        self.assertContains(response, "data-submit-button")
        self.assertContains(response, "Signing in...")
        self.assertNotContains(response, "<ul class=\"errorlist\">")

    def test_invalid_credentials_show_non_field_error_and_keep_username(self):
        response = self.client.post(
            self.login_url,
            {"username": "pharmacist", "password": "incorrect-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unable to sign in")
        self.assertContains(
            response,
            "Please enter a correct username and password.",
        )
        self.assertContains(response, 'value="pharmacist"')

    def test_empty_submission_shows_field_errors(self):
        response = self.client.post(
            self.login_url,
            {"username": "", "password": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.", count=2)
        self.assertContains(response, 'aria-invalid="true"', count=2)

    def test_valid_login_uses_django_authentication_and_redirects(self):
        response = self.client.post(
            self.login_url,
            {"username": "pharmacist", "password": "test-password"},
        )

        self.assertRedirects(response, reverse("dashboard:home"))
        self.assertEqual(
            int(self.client.session["_auth_user_id"]),
            self.user.pk,
        )

    def test_authenticated_user_is_redirected_to_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.get(self.login_url)

        self.assertRedirects(response, reverse("dashboard:home"))


class LogoutViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="pharmacist",
            password="test-password",
        )
        self.client.force_login(self.user)

    def test_logout_rejects_get(self):
        response = self.client.get(reverse("accounts:logout"))

        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_logout_accepts_post(self):
        response = self.client.post(reverse("accounts:logout"))

        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_dashboard_logout_uses_confirmation_modal_and_loading_state(self):
        response = self.client.get(reverse("dashboard:home"))

        self.assertContains(response, 'href="/static/logo-icon.png"')
        self.assertContains(response, 'src="/static/logo-white.png"')
        self.assertNotContains(response, "favicon.svg")
        self.assertContains(
            response,
            'data-modal-open="sidebar-logout-confirmation"',
        )
        self.assertContains(response, 'id="sidebar-logout-confirmation"')
        self.assertContains(
            response,
            f'action="{reverse("accounts:logout")}"',
        )
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, "Sign out")
        self.assertContains(response, "Signing out...")
