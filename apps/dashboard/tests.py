from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase
from django.urls import resolve

from config.context_processors import dashboard_navigation


class DashboardNavigationTests(TestCase):
    role_items = {
        "Owner / Admin": {
            "Dashboard",
            "Sales",
            "Medicines",
            "Inventory",
            "Suppliers",
            "Customers",
            "Prescriptions",
            "Purchases",
            "Invoices",
            "Payments",
            "Returns & Refunds",
            "Reports",
            "Settings",
            "Logout",
        },
        "Pharmacist": {
            "Dashboard",
            "Sales",
            "Medicines",
            "Inventory",
            "Customers",
            "Prescriptions",
            "Invoices",
            "Returns & Refunds",
            "Logout",
        },
        "Inventory Manager": {
            "Dashboard",
            "Medicines",
            "Inventory",
            "Suppliers",
            "Purchases",
            "Logout",
        },
        "Accountant": {
            "Dashboard",
            "Invoices",
            "Payments",
            "Reports",
            "Logout",
        },
    }

    def navigation_for(self, role_name):
        group = Group.objects.create(name=role_name)
        user = get_user_model().objects.create_user(
            username=role_name.lower().replace(" ", "-").replace("/", ""),
            password="test-password",
        )
        user.groups.add(group)

        request = RequestFactory().get("/")
        request.user = user
        request.resolver_match = resolve("/")
        return dashboard_navigation(request)["dashboard_navigation"]

    def test_navigation_preserves_role_visibility(self):
        for role_name, expected_labels in self.role_items.items():
            with self.subTest(role=role_name):
                items = self.navigation_for(role_name)
                self.assertEqual({item["label"] for item in items}, expected_labels)

    def test_dashboard_is_active_and_future_modules_are_disabled(self):
        items = self.navigation_for("Owner / Admin")
        dashboard = next(item for item in items if item["label"] == "Dashboard")
        future_items = [
            item
            for item in items
            if item["label"] not in {"Dashboard", "Logout"}
        ]

        self.assertTrue(dashboard["is_active"])
        self.assertEqual(dashboard["url"], "/")
        self.assertTrue(all(item["url"] is None for item in future_items))

    def test_sections_and_post_logout_are_exposed_to_the_template(self):
        items = self.navigation_for("Owner / Admin")
        logout_item = next(item for item in items if item["label"] == "Logout")

        self.assertEqual(
            {item["section"] for item in items},
            {"Main", "Management", "Transactions", "Reports", "System"},
        )
        self.assertEqual(logout_item["url"], "/accounts/logout/")
        self.assertEqual(logout_item["method"], "post")
