from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine
from apps.core.models import PharmacySettings
from apps.inventory.models import MedicineBatch
from apps.parties.models import Supplier
from apps.purchasing.models import PurchaseInvoice

from .queries import dashboard_context


class DashboardQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="dashboard-reader")
        cls.category = Category.objects.create(name="Dashboard category")
        cls.manufacturer = Manufacturer.objects.create(name="Dashboard manufacturer")
        cls.supplier = Supplier.objects.create(name="Private supplier")
        cls.pharmacy = PharmacySettings.objects.create(
            pharmacy_name="Test pharmacy", currency_code="USD",
            default_low_stock_threshold=Decimal("5"), expiry_warning_days=90,
        )

    def grant(self, *permissions):
        for name in permissions:
            app, codename = name.split(".")
            self.user.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=codename))
        self.user = get_user_model().objects.get(pk=self.user.pk)

    def medicine(self, name="Test medicine", threshold=None, active=True):
        return Medicine.objects.create(
            name=name, category=self.category, manufacturer=self.manufacturer,
            low_stock_threshold_base=threshold, is_active=active,
        )

    def batch(self, medicine, quantity="1", days=365, active=True):
        return MedicineBatch.objects.create(
            medicine=medicine, batch_number=f"B-{MedicineBatch.objects.count()}",
            quantity_available_base=Decimal(quantity),
            expiry_date=timezone.localdate() + timedelta(days=days),
            acquisition_cost_per_base_unit=Decimal("1"),
            first_received_at=timezone.now(), is_active=active,
        )

    def purchase(self, number, when, status=PurchaseInvoice.Status.POSTED):
        return PurchaseInvoice.objects.create(
            invoice_number=number, supplier=self.supplier,
            supplier_name_snapshot="Historical supplier", invoice_date=when.date(),
            status=status, posted_at=when, created_by=self.user, currency_code="USD",
            grand_total=Decimal("42.50"), remaining_balance=Decimal("42.50"),
        )

    def test_stock_partition_uses_fefo_threshold_equality_and_fallback(self):
        self.grant("inventory.view_medicinebatch")
        self.batch(self.medicine("Healthy", threshold=5), quantity="6")
        self.batch(self.medicine("At threshold", threshold=3), quantity="3")
        self.batch(self.medicine("Fallback"), quantity="4")
        self.batch(self.medicine("Explicit zero", threshold=0), quantity="0.001")
        multiple = self.medicine("Combined batches", threshold=5)
        self.batch(multiple, quantity="3")
        self.batch(multiple, quantity="3", days=0)
        self.medicine("No batches")
        self.batch(self.medicine("Expired only"), quantity="100", days=-1)
        self.batch(self.medicine("Inactive batch"), quantity="100", active=False)
        self.batch(self.medicine("Zero quantity"), quantity="0")
        self.batch(self.medicine("Inactive medicine", active=False), quantity="100")

        context = dashboard_context(self.user)
        self.assertEqual(context["inventory_metrics"], {
            "active": 9, "healthy": 3, "low": 2, "out": 4, "expired": 1, "near_expiry": 1,
        })
        self.assertEqual([item["value"] for item in context["kpis"]], [9, 2, 4, 1])
        self.assertEqual(context["stock_chart_data"]["values"], [3, 2, 4])
        self.assertEqual(context["stock_chart_data"]["labels"], ["Healthy", "Low stock", "Out of stock"])
        self.assertTrue(context["stock_chart_data"]["has_data"])
        self.assertTrue(all(item["status"] == "Out of stock" for item in context["attention_items"] if item["group"] == "Stock"))

    def test_expiry_includes_remaining_inactive_stock_and_inclusive_boundaries(self):
        self.grant("inventory.view_medicinebatch")
        medicine = self.medicine()
        for days in (-1, 0, 30, 31, 90, 91):
            self.batch(medicine, days=days)
        self.batch(medicine, quantity="0", days=-10)
        self.batch(medicine, days=-2, active=False)
        self.batch(self.medicine(active=False), days=30)
        context = dashboard_context(self.user)
        self.assertEqual(context["expiry_chart_data"]["values"], [2, 3, 2, 1])
        self.assertEqual(context["inventory_metrics"]["near_expiry"], 5)
        items = [item for item in context["attention_items"] if item["group"] == "Expiry"]
        self.assertEqual([item["status_variant"] for item in items], ["destructive", "destructive", "warning"])
        self.assertTrue(all("url" not in item for item in items))

    def test_configurable_warning_window_handles_zero_short_and_long_windows(self):
        self.grant("inventory.view_medicinebatch")
        medicine = self.medicine()
        for days in (-1, 0, 1, 15, 30, 31, 45, 46):
            self.batch(medicine, days=days)
        for window, labels, values in (
            (0, ["Expired", "Today", "1+ days"], [1, 1, 6]),
            (15, ["Expired", "0–15 days", "16+ days"], [1, 3, 4]),
            (45, ["Expired", "0–30 days", "31–45 days", "46+ days"], [1, 4, 2, 1]),
        ):
            with self.subTest(window=window):
                PharmacySettings.objects.update(expiry_warning_days=window)
                chart = dashboard_context(self.user)["expiry_chart_data"]
                self.assertEqual(chart["labels"], labels)
                self.assertEqual(chart["values"], values)

    def test_empty_inventory_has_zero_kpis_and_does_not_create_settings(self):
        self.grant("inventory.view_medicinebatch")
        PharmacySettings.objects.all().delete()
        context = dashboard_context(self.user)
        self.assertEqual([item["value"] for item in context["kpis"]], [0, 0, 0, 0])
        self.assertFalse(context["stock_chart_data"]["has_data"])
        self.assertFalse(context["expiry_chart_data"]["has_data"])
        self.assertFalse(PharmacySettings.objects.exists())
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "No active medicines are available yet.")
        self.assertNotContains(response, "<canvas")

    def test_missing_settings_uses_model_defaults_for_existing_stock(self):
        self.grant("inventory.view_medicinebatch")
        PharmacySettings.objects.all().delete()
        self.batch(self.medicine(), quantity="0.001", days=90)
        context = dashboard_context(self.user)
        self.assertEqual(context["stock_chart_data"]["values"], [1, 0, 0])
        self.assertEqual(context["inventory_metrics"]["near_expiry"], 1)

    def test_permissions_exclude_queries_context_and_embedded_json(self):
        self.batch(self.medicine("Private medicine"))
        self.purchase("PRIVATE-42", timezone.now())
        # Warm Django's permission cache so only dashboard reads are measured.
        self.user.get_all_permissions()
        with self.assertNumQueries(0):
            context = dashboard_context(self.user)
        self.assertEqual(context, {"kpis": [], "attention_items": [], "recent_activity": [], "charts": []})
        for permissions, allowed, denied in (
            (("inventory.view_medicinebatch",), "Stock Health", "PRIVATE-42"),
            (("purchasing.view_purchaseinvoice",), "PRIVATE-42", "stock-health-data"),
            (("finance.view_financial_reports",), "Sales, payments", "PRIVATE-42"),
        ):
            self.user.user_permissions.clear()
            self.grant(*permissions)
            self.client.force_login(self.user)
            response = self.client.get(reverse("dashboard:home"))
            self.assertContains(response, allowed)
            self.assertNotContains(response, denied)
            if "inventory.view_medicinebatch" not in permissions:
                self.assertNotContains(response, "Private medicine")

    def test_attention_links_require_catalog_permission_and_escape_names(self):
        medicine = self.medicine("</script><script>alert(1)</script>")
        self.grant("inventory.view_medicinebatch")
        self.assertIsNone(dashboard_context(self.user)["attention_items"][0]["url"])
        self.grant("catalog.view_medicine")
        self.assertEqual(dashboard_context(self.user)["attention_items"][0]["url"], reverse("catalog:medicine-detail", args=[medicine.pk]))
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, 'type="application/json"')
        self.assertContains(response, 'aria-describedby="stock-health-data-summary"')
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_recent_receipts_order_by_posted_time_and_use_snapshot_and_currency(self):
        self.grant("purchasing.view_purchaseinvoice")
        now = timezone.now()
        for index in range(7):
            self.purchase(f"PI-{index}", now - timedelta(days=index * 35))
        self.purchase("DRAFT", now, PurchaseInvoice.Status.DRAFT)
        self.purchase("VOID", now, PurchaseInvoice.Status.VOID)
        context = dashboard_context(self.user)
        self.assertEqual([item["reference"] for item in context["recent_activity"]], [f"PI-{index}" for index in range(5)])
        self.assertEqual(context["recent_activity"][0]["amount"], "USD 42.50")
        self.assertEqual(context["recent_activity"][0]["party"], "Historical supplier")
        chart = context["purchase_chart_data"]
        self.assertEqual(sum(chart["values"]), 7)
        self.assertEqual(len(chart["values"]), 12)
        self.assertIn(0, chart["values"])

    def test_purchase_chart_is_omitted_without_multiple_months(self):
        self.grant("purchasing.view_purchaseinvoice")
        self.assertNotIn("purchase_chart_data", dashboard_context(self.user))
        self.purchase("ONE", timezone.now())
        context = dashboard_context(self.user)
        self.assertNotIn("purchase_chart_data", context)
        self.assertEqual(len(context["recent_activity"]), 1)

    def test_local_day_drives_expiry_and_month_boundaries(self):
        self.grant("inventory.view_medicinebatch", "purchasing.view_purchaseinvoice")
        midnight = datetime(2026, 9, 1, 0, 30, tzinfo=datetime_timezone.utc)
        medicine = self.medicine()
        with timezone.override("America/Los_Angeles"), patch("django.utils.timezone.now", return_value=midnight):
            self.batch(medicine, days=0)
            self.purchase("AUG", midnight)
            self.purchase("JUL", datetime(2026, 7, 15, 12, tzinfo=datetime_timezone.utc))
            context = dashboard_context(self.user)
            self.assertEqual(context["inventory_metrics"]["expired"], 0)
            self.assertEqual(context["inventory_metrics"]["near_expiry"], 1)
            self.assertEqual(context["purchase_chart_data"]["labels"][-1], "Aug 2026")

    def test_query_count_is_bounded_as_records_grow(self):
        self.grant("inventory.view_medicinebatch", "purchasing.view_purchaseinvoice", "catalog.view_medicine")
        self.user.get_all_permissions()
        self.batch(self.medicine(), days=-1)
        self.purchase("FIRST", timezone.now())
        with CaptureQueriesContext(connection) as small:
            dashboard_context(self.user)
        for index in range(10):
            self.batch(self.medicine(f"Medicine {index}"), days=-1)
            self.purchase(f"MORE-{index}", timezone.now() - timedelta(days=35 * index))
        with CaptureQueriesContext(connection) as large:
            context = dashboard_context(self.user)
        self.assertEqual(len(small), len(large))
        self.assertLessEqual(len(large), 7)
        self.assertLessEqual(len(context["attention_items"]), 6)
