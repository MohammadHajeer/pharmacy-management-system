from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


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
