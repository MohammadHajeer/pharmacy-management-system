from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import resolve, reverse

from . import sample_data


class DashboardPreviewViewTests(TestCase):
    def setUp(self):
        self.preview_url = reverse("dashboard_preview:home")
        self.user = get_user_model().objects.create_superuser(
            username="dashboard-preview-user",
            password="test-password",
            email="preview@example.com",
        )

    def test_preview_has_its_own_route_and_template(self):
        self.client.force_login(self.user)

        response = self.client.get(self.preview_url)

        self.assertEqual(self.preview_url, "/dashboard-preview/")
        self.assertEqual(
            resolve(self.preview_url).view_name,
            "dashboard_preview:home",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard_preview/index.html")
        self.assertContains(response, "Visual comparison")

    def test_preview_keeps_its_own_illustrative_records(self):
        self.client.force_login(self.user)

        response = self.client.get(self.preview_url)

        self.assertEqual(response.context["kpis"], list(sample_data.SAMPLE_KPIS))
        self.assertEqual(
            response.context["recent_activity"],
            list(sample_data.SAMPLE_RECENT_ACTIVITY),
        )
        self.assertEqual(
            response.context["attention_items"],
            list(sample_data.SAMPLE_ATTENTION_ITEMS),
        )

    def test_preview_matches_existing_dashboard_auth_boundary(self):
        response = self.client.get(self.preview_url)

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={self.preview_url}",
        )
