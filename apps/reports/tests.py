from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine
from apps.core.models import PaymentMethod, PharmacySettings
from apps.finance.models import CustomerPayment, PaymentStatus, SupplierPayment
from apps.inventory.models import MedicineBatch
from apps.parties.models import Customer, Supplier
from apps.purchasing.models import PurchaseInvoice
from apps.returns.models import CustomerRefund, CustomerReturn, SupplierReturn
from apps.sales.models import SalesInvoice

from .queries import (
    completed_sales_report,
    customer_receivables_report,
    expiry_report,
    payment_activity_report,
    posted_purchases_report,
    returns_report,
    stock_report,
    supplier_payables_report,
)


class ReportsSchemaTests(SimpleTestCase):
    def test_reports_app_has_no_models(self):
        self.assertEqual(list(apps.get_app_config("reports").get_models()), [])


class ReportFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        cls.now = timezone.now()
        cls.user = get_user_model().objects.create_user("reporter", password="test-pass")
        cls.category = Category.objects.create(name="Analgesics")
        cls.manufacturer = Manufacturer.objects.create(name="PHARMANEX Labs")
        cls.medicine = Medicine.objects.create(
            name="Paracetamol", generic_name="Acetaminophen",
            category=cls.category, manufacturer=cls.manufacturer,
            low_stock_threshold_base=Decimal("10.000"),
            default_selling_price=Decimal("1.0000"),
        )
        cls.low_medicine = Medicine.objects.create(
            name="Ibuprofen", generic_name="Ibuprofen",
            category=cls.category, manufacturer=cls.manufacturer,
            low_stock_threshold_base=Decimal("10.000"),
            default_selling_price=Decimal("1.5000"),
        )
        cls.customer = Customer.objects.create(code="CUS-1", name="Ada Lovelace")
        cls.supplier = Supplier.objects.create(code="SUP-1", name="Med Supply")
        cls.method = PaymentMethod.objects.create(code="CASH", name="Cash")
        PharmacySettings.objects.create(
            pharmacy_name="PHARMANEX", currency_code="USD",
            default_low_stock_threshold=Decimal("5.000"),
        )

        cls.unpaid_sale = cls.make_sale("SAL-UNPAID", Decimal("100.00"), customer=cls.customer)
        cls.partial_sale = cls.make_sale("SAL-PARTIAL", Decimal("100.00"), customer=cls.customer)
        cls.paid_sale = cls.make_sale("SAL-PAID", Decimal("100.00"), customer=cls.customer)
        cls.walkin_sale = cls.make_sale(
            "SAL-WALKIN", Decimal("50.00"), customer=None,
            paid=Decimal("50.00"), balance=Decimal("0.00"),
        )
        cls.draft_sale = SalesInvoice.objects.create(
            pharmacist=cls.user, customer=cls.customer, currency_code="USD",
            grand_total=Decimal("999.00"), balance_due=Decimal("999.00"),
        )
        CustomerPayment.objects.create(
            sales_invoice=cls.partial_sale, customer=cls.customer,
            payment_method=cls.method, amount=Decimal("40.00"),
            processed_by=cls.user, paid_at=cls.now, status=PaymentStatus.POSTED,
        )
        cls.reversed_customer_payment = CustomerPayment.objects.create(
            sales_invoice=cls.partial_sale, customer=cls.customer,
            payment_method=cls.method, amount=Decimal("20.00"),
            processed_by=cls.user, paid_at=cls.now - timedelta(minutes=1),
            status=PaymentStatus.REVERSED, reversed_by=cls.user,
            reversed_at=cls.now, reversal_reason="Duplicate",
        )
        CustomerPayment.objects.create(
            sales_invoice=cls.paid_sale, customer=cls.customer,
            payment_method=cls.method, amount=Decimal("100.00"),
            processed_by=cls.user, paid_at=cls.now, status=PaymentStatus.POSTED,
        )

        cls.unpaid_purchase = cls.make_purchase("PUR-UNPAID", Decimal("80.00"))
        cls.partial_purchase = cls.make_purchase("PUR-PARTIAL", Decimal("80.00"))
        cls.paid_purchase = cls.make_purchase("PUR-PAID", Decimal("80.00"))
        cls.draft_purchase = PurchaseInvoice.objects.create(
            supplier=cls.supplier, invoice_date=cls.today, currency_code="USD",
            grand_total=Decimal("888.00"), remaining_balance=Decimal("888.00"),
            created_by=cls.user,
        )
        SupplierPayment.objects.create(
            purchase_invoice=cls.partial_purchase, supplier=cls.supplier,
            payment_method=cls.method, amount=Decimal("30.00"),
            processed_by=cls.user, paid_at=cls.now, status=PaymentStatus.POSTED,
        )
        cls.reversed_supplier_payment = SupplierPayment.objects.create(
            purchase_invoice=cls.partial_purchase, supplier=cls.supplier,
            payment_method=cls.method, amount=Decimal("10.00"),
            processed_by=cls.user, paid_at=cls.now - timedelta(minutes=1),
            status=PaymentStatus.REVERSED, reversed_by=cls.user,
            reversed_at=cls.now, reversal_reason="Correction",
        )
        SupplierPayment.objects.create(
            purchase_invoice=cls.paid_purchase, supplier=cls.supplier,
            payment_method=cls.method, amount=Decimal("80.00"),
            processed_by=cls.user, paid_at=cls.now, status=PaymentStatus.POSTED,
        )

        cls.healthy_batch = cls.make_batch("HEALTHY", cls.today + timedelta(days=180), "20.000")
        cls.low_batch = cls.make_batch(
            "LOW", cls.today + timedelta(days=60), "2.000", medicine=cls.low_medicine
        )
        cls.empty_batch = cls.make_batch("EMPTY", cls.today + timedelta(days=120), "0.000")
        cls.expired_batch = cls.make_batch("EXPIRED", cls.today - timedelta(days=1), "3.000")
        cls.near_batch = cls.make_batch("NEAR", cls.today + timedelta(days=30), "4.000")

        cls.customer_return = CustomerReturn.objects.create(
            return_number="CRT-1", sales_invoice=cls.partial_sale,
            customer=cls.customer, reason="Damaged pack",
            return_total=Decimal("12.00"), status="POSTED",
            processed_by=cls.user, posted_at=cls.now,
        )
        cls.refund = CustomerRefund.objects.create(
            refund_number="CRF-1", customer_return=cls.customer_return,
            sales_invoice=cls.partial_sale, payment_method=cls.method,
            amount=Decimal("12.00"), processed_by=cls.user, refunded_at=cls.now,
        )
        cls.supplier_return = SupplierReturn.objects.create(
            return_number="SRT-1", supplier=cls.supplier,
            purchase_invoice=cls.partial_purchase, reason="Recall",
            return_total=Decimal("8.00"), status="POSTED",
            processed_by=cls.user, posted_at=cls.now,
        )

    @classmethod
    def make_sale(cls, number, total, *, customer, paid=Decimal("0.00"), balance=None, completed_at=None):
        balance = total - paid if balance is None else balance
        return SalesInvoice.objects.create(
            invoice_number=number, status=SalesInvoice.Status.COMPLETED,
            customer=customer, pharmacist=cls.user,
            customer_name_snapshot=customer.name if customer else "",
            currency_code="USD", grand_total=total, paid_total=paid,
            balance_due=balance,
            payment_status=SalesInvoice.PaymentStatus.PAID if balance == 0 else SalesInvoice.PaymentStatus.UNPAID,
            completed_at=completed_at or cls.now,
        )

    @classmethod
    def make_purchase(cls, number, total, *, invoice_date=None):
        return PurchaseInvoice.objects.create(
            invoice_number=number, supplier=cls.supplier,
            supplier_name_snapshot=cls.supplier.name,
            invoice_date=invoice_date or cls.today, status=PurchaseInvoice.Status.POSTED,
            currency_code="USD", grand_total=total, remaining_balance=total,
            created_by=cls.user, posted_by=cls.user, posted_at=cls.now,
        )

    @classmethod
    def make_batch(cls, number, expiry, quantity, *, medicine=None):
        return MedicineBatch.objects.create(
            medicine=medicine or cls.medicine, batch_number=number, expiry_date=expiry,
            acquisition_cost_per_base_unit=Decimal("0.5000"),
            quantity_available_base=Decimal(quantity), first_received_at=cls.now,
        )

    @classmethod
    def grant(cls, user, *codenames):
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))


class ReportQueryTests(ReportFixtureMixin, TestCase):
    def test_sales_excludes_drafts_and_applies_completed_date_range(self):
        old = self.make_sale(
            "SAL-OLD", Decimal("10.00"), customer=self.customer,
            completed_at=self.now - timedelta(days=10),
        )
        result = completed_sales_report({"date_from": self.today.isoformat()})
        ids = set(result.rows.values_list("pk", flat=True))
        self.assertNotIn(self.draft_sale.pk, ids)
        self.assertNotIn(old.pk, ids)
        self.assertIn(self.unpaid_sale.pk, ids)
        self.assertEqual(result.summary["total"], Decimal("350.00"))

    def test_purchases_excludes_drafts_and_uses_invoice_dates(self):
        old = self.make_purchase("PUR-OLD", Decimal("10.00"), invoice_date=self.today - timedelta(days=10))
        result = posted_purchases_report({"date_from": self.today.isoformat()})
        ids = set(result.rows.values_list("pk", flat=True))
        self.assertNotIn(self.draft_purchase.pk, ids)
        self.assertNotIn(old.pk, ids)
        self.assertEqual(result.summary["count"], 3)

    def test_stock_states_and_expiry_buckets_use_batch_truth(self):
        stock = {row.batch_number: row for row in stock_report({}).rows}
        self.assertEqual(stock["EMPTY"].stock_state, "out")
        self.assertEqual(stock["EXPIRED"].stock_state, "expired")
        self.assertEqual(stock["LOW"].stock_state, "low")
        self.assertEqual(stock["HEALTHY"].stock_state, "healthy")
        expiry = {row.batch_number: row.expiry_bucket for row in expiry_report({}).rows}
        self.assertEqual(expiry["EXPIRED"], "expired")
        self.assertEqual(expiry["NEAR"], "within_30")
        self.assertEqual(expiry["LOW"], "days_31_90")
        self.assertEqual(expiry["HEALTHY"], "later")
        self.assertNotIn("EMPTY", expiry)

    def test_receivables_use_only_active_posted_payments(self):
        result = customer_receivables_report({})
        balances = {row.invoice_number: row.effective_balance for row in result.rows}
        self.assertEqual(balances["SAL-UNPAID"], Decimal("100.00"))
        self.assertEqual(balances["SAL-PARTIAL"], Decimal("60.00"))
        self.assertNotIn("SAL-PAID", balances)
        self.assertNotIn("SAL-WALKIN", balances)
        self.assertEqual(result.summary["outstanding"], Decimal("160.00"))

    def test_payables_use_only_active_posted_payments(self):
        result = supplier_payables_report({})
        balances = {row.invoice_number: row.effective_balance for row in result.rows}
        self.assertEqual(balances["PUR-UNPAID"], Decimal("80.00"))
        self.assertEqual(balances["PUR-PARTIAL"], Decimal("50.00"))
        self.assertNotIn("PUR-PAID", balances)
        self.assertEqual(result.summary["outstanding"], Decimal("130.00"))

    def test_payment_activity_retains_reversals_but_excludes_them_from_active_value(self):
        result = payment_activity_report({})
        self.assertEqual(result.summary["count"], 6)
        self.assertEqual(result.summary["reversed"], 2)
        self.assertEqual(result.summary["customer_active"], Decimal("140.00"))
        self.assertEqual(result.summary["supplier_active"], Decimal("110.00"))

    def test_returns_report_represents_each_authoritative_record_type(self):
        result = returns_report({})
        self.assertEqual(
            {row["kind"] for row in result.rows},
            {"customer_return", "customer_refund", "supplier_return"},
        )
        self.assertEqual(returns_report({"q": "not-present"}).rows, [])

    def test_invalid_date_range_returns_clean_error_and_no_rows(self):
        result = completed_sales_report({"date_from": "2026-09-02", "date_to": "2026-09-01"})
        self.assertIn("date_to", result.errors)
        self.assertEqual(result.summary["count"], 0)


class ReportViewTests(ReportFixtureMixin, TestCase):
    def setUp(self):
        self.client.force_login(self.user)

    def test_finance_report_requires_financial_report_permission(self):
        self.assertEqual(self.client.get(reverse("reports:receivables")).status_code, 403)
        self.grant(self.user, "view_financial_reports")
        response = self.client.get(reverse("reports:receivables"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Outstanding receivable")

    def test_hub_only_lists_reports_the_user_can_open(self):
        self.grant(self.user, "view_medicinebatch")
        response = self.client.get(reverse("reports:hub"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stock Report")
        self.assertContains(response, "Expiry Report")
        self.assertNotContains(response, "Customer Receivables")
        self.assertNotContains(response, "Sales Report")

    def test_every_authorized_report_workspace_renders(self):
        self.grant(
            self.user,
            "view_salesinvoice",
            "view_purchaseinvoice",
            "view_medicinebatch",
            "view_financial_reports",
            "view_customerreturn",
            "view_supplierreturn",
        )
        for url_name in (
            "reports:hub", "reports:sales", "reports:purchases", "reports:stock",
            "reports:expiry", "reports:receivables", "reports:payables",
            "reports:payments", "reports:returns",
        ):
            with self.subTest(url_name=url_name):
                self.assertEqual(self.client.get(reverse(url_name)).status_code, 200)

    def test_returns_report_hides_unavailable_supplier_records(self):
        self.grant(self.user, "view_customerreturn")
        response = self.client.get(reverse("reports:returns"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CRT-1")
        self.assertContains(response, "CRF-1")
        self.assertNotContains(response, "SRT-1")

    def test_purchase_report_hides_payable_totals_without_finance_permission(self):
        self.grant(self.user, "view_purchaseinvoice")
        response = self.client.get(reverse("reports:purchases"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Outstanding payable")
        self.assertNotContains(response, "Effective paid")
        self.grant(self.user, "view_financial_reports")
        response = self.client.get(reverse("reports:purchases"))
        self.assertContains(response, "Outstanding payable")
        self.assertContains(response, "Effective paid")

    def test_sales_report_filters_and_preserves_query_through_pagination(self):
        self.grant(self.user, "view_salesinvoice")
        for index in range(26):
            self.make_sale(f"SAL-BULK-{index:02}", Decimal("1.00"), customer=self.customer)
        response = self.client.get(reverse("reports:sales"), {"q": "SAL-BULK"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["report_rows"]), 25)
        self.assertContains(response, "q=SAL-BULK")
        self.assertContains(response, "page=2")

    def test_invalid_dates_render_accessible_filter_error(self):
        self.grant(self.user, "view_salesinvoice")
        response = self.client.get(
            reverse("reports:sales"),
            {"date_from": "2026-09-02", "date_to": "2026-09-01"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Date to must be on or after date from.")
        self.assertContains(response, 'aria-invalid="true"')

    def test_anonymous_report_access_redirects_to_login(self):
        self.client.logout()
        response = self.client.get(reverse("reports:stock"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
