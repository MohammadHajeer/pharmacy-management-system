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

from apps.catalog.models import Category, Manufacturer, Medicine, MedicineUnit
from apps.core.models import PaymentMethod, PharmacySettings
from apps.finance.models import CustomerPayment, PaymentStatus
from apps.inventory.models import MedicineBatch
from apps.parties.models import Customer, Supplier
from apps.purchasing.models import PurchaseInvoice
from apps.sales.models import SalesInvoice, SalesInvoiceLine

from .queries import dashboard_context


class DashboardQueryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="dashboard-reader")
        cls.category = Category.objects.create(name="Dashboard category")
        cls.manufacturer = Manufacturer.objects.create(name="Dashboard manufacturer")
        cls.supplier = Supplier.objects.create(name="Private supplier")
        cls.customer = Customer.objects.create(
            code="DASH-CUSTOMER", name="Dashboard customer"
        )
        cls.payment_method = PaymentMethod.objects.create(
            code="DASH-CASH", name="Dashboard cash"
        )
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

    def sale(
        self,
        number,
        when,
        *,
        status=SalesInvoice.Status.COMPLETED,
        total="100.00",
        paid="0.00",
        customer=None,
    ):
        total = Decimal(total)
        paid = Decimal(paid)
        if customer is None and status == SalesInvoice.Status.COMPLETED and not paid:
            paid = total
        if paid == total:
            payment_status = SalesInvoice.PaymentStatus.PAID
        elif paid:
            payment_status = SalesInvoice.PaymentStatus.PARTIAL
        else:
            payment_status = SalesInvoice.PaymentStatus.UNPAID
        return SalesInvoice.objects.create(
            invoice_number=number,
            status=status,
            customer=customer,
            pharmacist=self.user,
            customer_name_snapshot=customer.name if customer else "",
            currency_code="USD",
            subtotal=total,
            grand_total=total,
            paid_total=paid,
            balance_due=total - paid,
            payment_status=payment_status,
            completed_at=when,
        )

    def sale_line(self, invoice, medicine, quantity):
        unit, _ = MedicineUnit.objects.get_or_create(
            medicine=medicine,
            name="unit",
            defaults={
                "conversion_to_base": Decimal("1.000000"),
                "is_base_unit": True,
            },
        )
        quantity = Decimal(quantity)
        return SalesInvoiceLine.objects.create(
            sales_invoice=invoice,
            medicine=medicine,
            medicine_description_snapshot=medicine.name,
            medicine_unit=unit,
            unit_name_snapshot=unit.name,
            quantity=quantity,
            conversion_to_base_snapshot=Decimal("1.000000"),
            requested_quantity_base=quantity,
            unit_price=Decimal("1.0000"),
            line_total=quantity,
        )

    def payment(
        self,
        invoice,
        amount,
        *,
        status=PaymentStatus.POSTED,
        method=None,
        when=None,
    ):
        return CustomerPayment.objects.create(
            sales_invoice=invoice,
            customer=invoice.customer,
            payment_method=method or self.payment_method,
            amount=Decimal(amount),
            processed_by=self.user,
            paid_at=when or invoice.completed_at,
            status=status,
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

    def test_stock_focal_chip_tracks_the_most_urgent_populated_category(self):
        self.grant("inventory.view_medicinebatch")
        self.batch(self.medicine("Healthy"), quantity="10")
        for expected_index, expected_label, expected_tone in (
            (0, "Healthy", "healthy"), (1, "Low stock", "warning"), (2, "Out of stock", "danger"),
        ):
            if expected_index == 1:
                self.batch(self.medicine("Low"), quantity="1")
            elif expected_index == 2:
                self.medicine("Out")
            chart = dashboard_context(self.user)["stock_chart_data"]
            with self.subTest(label=expected_label):
                self.assertEqual(chart["focus_index"], expected_index)
                self.assertEqual(chart["focus"], {"label": expected_label, "value": 1, "tone": expected_tone})
                self.assertEqual(chart["focus"]["value"], chart["values"][expected_index])

    def test_expiry_focal_chip_tracks_existing_configurable_buckets(self):
        self.grant("inventory.view_medicinebatch")
        PharmacySettings.objects.update(expiry_warning_days=0)
        medicine = self.medicine()
        for days, expected_index, expected_label in ((1, 2, "1+ days"), (0, 1, "Today"), (-1, 0, "Expired")):
            self.batch(medicine, days=days)
            chart = dashboard_context(self.user)["expiry_chart_data"]
            with self.subTest(label=expected_label):
                self.assertEqual(chart["focus_index"], expected_index)
                self.assertEqual(chart["focus"]["label"], expected_label)
                self.assertEqual(chart["focus"]["value"], chart["values"][expected_index])

    def test_expiry_safe_bucket_is_separately_labeled_and_all_counts_remain_accessible(self):
        self.grant("inventory.view_medicinebatch")
        medicine = self.medicine()
        self.batch(medicine, days=100)
        self.client.force_login(self.user)
        for warning_days, safe_label in ((0, "1+ days"), (15, "16+ days"), (90, "91+ days")):
            PharmacySettings.objects.update(expiry_warning_days=warning_days)
            response = self.client.get(reverse("dashboard:home"))
            with self.subTest(warning_days=warning_days):
                chart = response.context["expiry_chart_data"]
                self.assertEqual(chart["values"][-1], 1)
                self.assertFalse(chart["horizontal"])
                self.assertFalse(response.context["stock_chart_data"]["horizontal"])
                self.assertContains(response, f"Beyond warning window · {safe_label}")
                self.assertContains(response, f"{safe_label}: 1 batches.")
                self.assertContains(response, "Expired &amp; within warning window")
                self.assertContains(response, 'aria-describedby="expiry-exposure-data-summary expiry-exposure-data-scope"')

    def test_follow_up_separates_and_escapes_batch_identifier_without_a_new_link(self):
        self.grant("inventory.view_medicinebatch")
        medicine = self.medicine("Medicine with a long descriptive name")
        batch = self.batch(medicine, days=-1)
        batch.batch_number = 'LOT-<script>alert("batch")</script>'
        batch.save(update_fields=["batch_number"])
        item = next(item for item in dashboard_context(self.user)["attention_items"] if item["group"] == "Expiry")
        self.assertEqual(item["title"], medicine.name)
        self.assertEqual(item["batch_number"], batch.batch_number)
        self.assertNotIn("url", item)
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "LOT-&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("batch")</script>')

    def test_ledger_retains_reference_amount_status_and_full_timestamp_in_four_columns(self):
        self.grant("purchasing.view_purchaseinvoice")
        reference = 'PUR-0123456789ABCDEF0123456789ABCDEF'
        invoice = self.purchase(reference, timezone.now())
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, f'title="{reference}"')
        self.assertContains(response, f'>{reference}</a>')
        self.assertContains(response, reverse("purchasing:purchase-invoice-detail", args=[invoice.pk]))
        self.assertContains(response, "USD 42.50")
        self.assertContains(response, "Posted")
        self.assertContains(response, "Historical supplier")
        self.assertContains(response, '<time datetime="')
        self.assertContains(response, 'scope="col"', count=4)
        self.assertContains(response, 'tabindex="0" role="region" aria-label="Recent activity ledger"')
        self.assertContains(response, "focus:whitespace-normal focus:wrap-anywhere")

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
            (("finance.view_financial_reports",), "Payment Method Mix", "PRIVATE-42"),
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
        self.assertEqual(len(context["recent_activity"]), 5)

    def test_local_day_drives_expiry_and_month_boundaries(self):
        self.grant(
            "inventory.view_medicinebatch",
            "finance.view_financial_reports",
        )
        midnight = datetime(2026, 9, 1, 0, 30, tzinfo=datetime_timezone.utc)
        medicine = self.medicine()
        with timezone.override("America/Los_Angeles"), patch("django.utils.timezone.now", return_value=midnight):
            self.batch(medicine, days=0)
            self.sale("AUG-SALE", midnight)
            self.purchase("AUG", midnight)
            self.purchase("JUL", datetime(2026, 7, 15, 12, tzinfo=datetime_timezone.utc))
            context = dashboard_context(self.user)
            self.assertEqual(context["inventory_metrics"]["expired"], 0)
            self.assertEqual(context["inventory_metrics"]["near_expiry"], 1)
            comparison = context["commercial_charts"][0]
            self.assertEqual(comparison["labels"][-1], "Aug 2026")

    def test_sales_months_include_completed_and_exclude_draft_and_void(self):
        self.grant("sales.view_salesinvoice")
        january = datetime(2026, 1, 15, 12, tzinfo=datetime_timezone.utc)
        march = datetime(2026, 3, 15, 12, tzinfo=datetime_timezone.utc)
        self.sale("COMPLETED-JAN", january, total="125.50")
        self.sale(
            "DRAFT-MAR",
            march,
            status=SalesInvoice.Status.DRAFT,
            total="900.00",
        )
        self.sale(
            "VOID-MAR",
            march,
            status=SalesInvoice.Status.VOID,
            total="700.00",
        )
        self.sale("COMPLETED-MAR", march, total="74.50")

        chart = dashboard_context(self.user)["commercial_charts"][0]

        self.assertEqual(chart["labels"], ["Jan 2026", "Feb 2026", "Mar 2026"])
        self.assertEqual(
            chart["values"],
            [Decimal("125.50"), Decimal("0.00"), Decimal("74.50")],
        )
        self.assertEqual([row["values"][1] for row in chart["rows"]], [1, 0, 1])
        self.assertNotIn(Decimal("900.00"), chart["values"])

    def test_purchase_comparison_uses_posted_only_and_shared_months(self):
        self.grant("finance.view_financial_reports", "sales.view_salesinvoice")
        january = datetime(2026, 1, 10, 12, tzinfo=datetime_timezone.utc)
        february = datetime(2026, 2, 10, 12, tzinfo=datetime_timezone.utc)
        march = datetime(2026, 3, 10, 12, tzinfo=datetime_timezone.utc)
        self.sale("JAN-SALE", january, total="100.00")
        self.sale("MAR-SALE", march, total="50.00")
        self.purchase("JAN-POSTED", january)
        self.purchase("FEB-DRAFT", february, PurchaseInvoice.Status.DRAFT)
        self.purchase("MAR-POSTED", march)

        sales_chart, chart = dashboard_context(self.user)["commercial_charts"]

        self.assertEqual(chart["labels"], ["Jan 2026", "Feb 2026", "Mar 2026"])
        self.assertEqual(chart["labels"], sales_chart["labels"])
        self.assertEqual(chart["datasets"][0]["values"], [Decimal("100.00"), Decimal("0.00"), Decimal("50.00")])
        self.assertEqual(chart["datasets"][1]["values"], [Decimal("42.50"), Decimal("0.00"), Decimal("42.50")])

    def test_payment_mix_and_receivables_use_only_effective_posted_payments(self):
        self.grant("finance.view_financial_reports")
        when = datetime(2026, 4, 10, 12, tzinfo=datetime_timezone.utc)
        partial = self.sale(
            "PARTIAL",
            when,
            customer=self.customer,
            total="100.00",
            paid="40.00",
        )
        self.payment(partial, "40.00")
        self.payment(partial, "15.00", status=PaymentStatus.REVERSED)
        self.sale(
            "UNPAID",
            when,
            customer=self.customer,
            total="50.00",
        )
        walk_in = self.sale("WALK-IN", when, total="25.00")
        self.payment(walk_in, "25.00")
        draft = self.sale(
            "DRAFT-CUSTOMER",
            when,
            status=SalesInvoice.Status.DRAFT,
            customer=self.customer,
            total="80.00",
        )
        self.payment(draft, "10.00")

        context = dashboard_context(self.user)
        payment_mix = context["finance_charts"][0]

        self.assertEqual(payment_mix["values"], [Decimal("75.00")])
        self.assertNotIn(Decimal("15.00"), payment_mix["values"])
        self.assertEqual(
            context["receivables"],
            {
                "total": Decimal("110.00"),
                "partial": 1,
                "unpaid": 1,
                "formatted_total": "USD 110.00",
                "has_data": True,
            },
        )

    def test_top_selling_uses_completed_sale_lines_and_base_quantity(self):
        self.grant("sales.view_salesinvoice")
        when = timezone.now()
        first = self.medicine("First medicine")
        second = self.medicine("Second medicine")
        self.sale_line(self.sale("FIRST-COMPLETE", when), first, "2")
        self.sale_line(self.sale("SECOND-COMPLETE", when), second, "3")
        self.sale_line(
            self.sale(
                "FIRST-DRAFT",
                when,
                status=SalesInvoice.Status.DRAFT,
                total="100.00",
            ),
            first,
            "100",
        )

        chart = dashboard_context(self.user)["performance_charts"][0]

        self.assertEqual(chart["labels"], ["Second medicine", "First medicine"])
        self.assertEqual(chart["values"], [Decimal("3"), Decimal("2")])

    def test_sales_and_finance_widgets_have_separate_permissions(self):
        when = timezone.now()
        self.sale("PRIVATE-SALE", when)
        self.payment_method.name = "Private card"
        self.payment_method.save(update_fields=["name"])

        self.grant("sales.view_salesinvoice")
        sales_context = dashboard_context(self.user)
        self.assertIn("commercial_charts", sales_context)
        self.assertIn("performance_charts", sales_context)
        self.assertNotIn("finance_charts", sales_context)
        self.assertNotIn("receivables", sales_context)

        self.user.user_permissions.clear()
        self.grant("finance.view_financial_reports")
        finance_context = dashboard_context(self.user)
        self.assertIn("finance_charts", finance_context)
        self.assertIn("receivables", finance_context)
        self.assertNotIn("performance_charts", finance_context)
        self.assertEqual(
            [chart["title"] for chart in finance_context["commercial_charts"]],
            ["Purchases vs Sales"],
        )

    def test_new_analytics_render_empty_states_without_chart_canvases(self):
        self.grant("sales.view_salesinvoice", "finance.view_financial_reports")
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard:home"))

        for message in (
            "No completed sales yet.",
            "No completed sales or posted purchases yet.",
            "No posted customer payments yet.",
            "No completed sale lines yet.",
            "No outstanding receivables.",
        ):
            self.assertContains(response, message)
        self.assertNotContains(response, "<canvas")

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
