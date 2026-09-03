from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine, MedicineUnit
from apps.core.models import PaymentMethod, PharmacySettings
from apps.finance.models import CustomerPayment, PaymentStatus, SupplierPayment
from apps.inventory.models import MedicineBatch
from apps.parties.models import Customer, Supplier
from apps.purchasing.models import PurchaseInvoice
from apps.returns.models import CustomerRefund, CustomerReturn, RefundStatus, ReturnStatus, SupplierReturn
from apps.sales.models import SaleBatchAllocation, SalesInvoice, SalesInvoiceLine

from .services import (
    FINANCIAL_REPORT_PERMISSION,
    cogs_and_gross_profit_report,
    current_inventory_report,
    customer_payments_report,
    customer_receivables_report,
    expired_stock_report,
    low_stock_report,
    near_expiry_report,
    purchases_report,
    sales_report,
    supplier_payables_report,
    supplier_payments_report,
)


def _grant(user, app_label, codename):
    permission = Permission.objects.get(content_type__app_label=app_label, codename=codename)
    user.user_permissions.add(permission)


class _ReportsFixtureMixin:
    @classmethod
    def _build_fixtures(cls):
        cls.pharmacist = get_user_model().objects.create_user(username="pharmacist-user")

        category = Category.objects.create(name="Pain relief")
        manufacturer = Manufacturer.objects.create(name="Example manufacturer")
        cls.medicine = Medicine.objects.create(
            name="Example tablet",
            category=category,
            manufacturer=manufacturer,
            default_selling_price=Decimal("10.0000"),
            low_stock_threshold_base=Decimal("5.000"),
        )
        cls.unit = MedicineUnit.objects.create(
            medicine=cls.medicine,
            name="Tablet",
            conversion_to_base=Decimal("1.000000"),
            is_base_unit=True,
        )
        cls.payment_method = PaymentMethod.objects.create(code="CASH", name="Cash")
        cls.customer = Customer.objects.create(code="CUST-1", name="Jane Customer")
        cls.supplier = Supplier.objects.create(code="SUPP-1", name="Acme Supplier")

        today = timezone.localdate()

        cls.low_batch = MedicineBatch.objects.create(
            medicine=cls.medicine,
            batch_number="BATCH-LOW",
            expiry_date=today + timedelta(days=400),
            acquisition_cost_per_base_unit=Decimal("4.0000"),
            quantity_available_base=Decimal("3.000"),
            first_received_at=timezone.now() - timedelta(days=30),
        )
        cls.near_expiry_batch = MedicineBatch.objects.create(
            medicine=cls.medicine,
            batch_number="BATCH-NEAR",
            expiry_date=today + timedelta(days=10),
            acquisition_cost_per_base_unit=Decimal("4.0000"),
            quantity_available_base=Decimal("2.000"),
            first_received_at=timezone.now() - timedelta(days=20),
        )
        cls.expired_batch = MedicineBatch.objects.create(
            medicine=cls.medicine,
            batch_number="BATCH-EXPIRED",
            expiry_date=today - timedelta(days=5),
            acquisition_cost_per_base_unit=Decimal("4.0000"),
            quantity_available_base=Decimal("1.000"),
            first_received_at=timezone.now() - timedelta(days=60),
        )

        now = timezone.now()

        cls.sales_invoice = SalesInvoice.objects.create(
            invoice_number="SAL-RPT0001",
            status=SalesInvoice.Status.COMPLETED,
            customer=cls.customer,
            pharmacist=cls.pharmacist,
            currency_code="USD",
            subtotal=Decimal("100.00"),
            discount_total=Decimal("0.00"),
            tax_total=Decimal("10.00"),
            grand_total=Decimal("110.00"),
            paid_total=Decimal("40.00"),
            balance_due=Decimal("70.00"),
            payment_status=SalesInvoice.PaymentStatus.PARTIAL,
            completed_at=now - timedelta(days=2),
        )
        cls.sales_line = SalesInvoiceLine.objects.create(
            sales_invoice=cls.sales_invoice,
            medicine=cls.medicine,
            medicine_description_snapshot=cls.medicine.name,
            medicine_unit=cls.unit,
            unit_name_snapshot=cls.unit.name,
            quantity=Decimal("10.000"),
            conversion_to_base_snapshot=Decimal("1.000000"),
            requested_quantity_base=Decimal("10.000"),
            unit_price=Decimal("10.0000"),
            line_total=Decimal("110.00"),
        )
        SaleBatchAllocation.objects.create(
            sales_invoice_line=cls.sales_line,
            batch=cls.low_batch,
            allocated_quantity_base=Decimal("6.000"),
            acquisition_cost_snapshot=Decimal("4.0000"),
        )
        SaleBatchAllocation.objects.create(
            sales_invoice_line=cls.sales_line,
            batch=cls.near_expiry_batch,
            allocated_quantity_base=Decimal("4.000"),
            acquisition_cost_snapshot=Decimal("4.5000"),
        )
        # COGS for this line = (6 * 4.0000) + (4 * 4.5000) = 24 + 18 = 42.00

        cls.customer_payment = CustomerPayment.objects.create(
            sales_invoice=cls.sales_invoice,
            customer=cls.customer,
            payment_method=cls.payment_method,
            amount=Decimal("40.00"),
            processed_by=cls.pharmacist,
            paid_at=now - timedelta(days=1),
            status=PaymentStatus.POSTED,
        )

        cls.customer_return = CustomerReturn.objects.create(
            return_number="CRT-RPT0001",
            sales_invoice=cls.sales_invoice,
            customer=cls.customer,
            reason="Damaged",
            return_total=Decimal("10.00"),
            status=ReturnStatus.POSTED,
            processed_by=cls.pharmacist,
            posted_at=now,
        )
        cls.customer_refund = CustomerRefund.objects.create(
            refund_number="CRF-RPT0001",
            customer_return=cls.customer_return,
            sales_invoice=cls.sales_invoice,
            payment_method=cls.payment_method,
            amount=Decimal("10.00"),
            processed_by=cls.pharmacist,
            refunded_at=now,
            status=RefundStatus.POSTED,
        )

        cls.purchase_invoice = PurchaseInvoice.objects.create(
            invoice_number="PUR-RPT0001",
            supplier=cls.supplier,
            invoice_date=today - timedelta(days=15),
            status=PurchaseInvoice.Status.POSTED,
            currency_code="USD",
            subtotal=Decimal("200.00"),
            grand_total=Decimal("200.00"),
            paid_total=Decimal("50.00"),
            remaining_balance=Decimal("150.00"),
            payment_status=PurchaseInvoice.PaymentStatus.PARTIAL,
            created_by=cls.pharmacist,
            posted_by=cls.pharmacist,
            posted_at=now - timedelta(days=14),
        )
        cls.supplier_payment = SupplierPayment.objects.create(
            purchase_invoice=cls.purchase_invoice,
            supplier=cls.supplier,
            payment_method=cls.payment_method,
            amount=Decimal("50.00"),
            processed_by=cls.pharmacist,
            paid_at=now - timedelta(days=13),
            status=PaymentStatus.POSTED,
        )
        cls.supplier_return = SupplierReturn.objects.create(
            return_number="SRT-RPT0001",
            supplier=cls.supplier,
            purchase_invoice=cls.purchase_invoice,
            reason="Expired",
            return_total=Decimal("20.00"),
            status=ReturnStatus.POSTED,
            processed_by=cls.pharmacist,
            posted_at=now - timedelta(days=12),
        )


class OperationalReportPermissionTests(_ReportsFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build_fixtures()
        cls.sales_viewer = get_user_model().objects.create_user(username="sales-viewer")
        _grant(cls.sales_viewer, "sales", "view_salesinvoice")
        cls.purchasing_viewer = get_user_model().objects.create_user(username="purchasing-viewer")
        _grant(cls.purchasing_viewer, "purchasing", "view_purchaseinvoice")
        cls.inventory_viewer = get_user_model().objects.create_user(username="inventory-viewer")
        _grant(cls.inventory_viewer, "inventory", "view_medicinebatch")
        cls.no_perms = get_user_model().objects.create_user(username="no-perms")

    def test_sales_report_requires_permission_and_reconciles_totals(self):
        with self.assertRaises(PermissionDenied):
            sales_report(actor=self.no_perms)
        report = sales_report(actor=self.sales_viewer)
        self.assertEqual(report["invoice_count"], 1)
        self.assertEqual(report["grand_total"], Decimal("110.00"))
        self.assertEqual(report["tax_total"], Decimal("10.00"))

    def test_sales_report_date_filter_excludes_out_of_range(self):
        future_only = sales_report(
            actor=self.sales_viewer,
            date_from=timezone.localdate() + timedelta(days=1),
        )
        self.assertEqual(future_only["invoice_count"], 0)
        self.assertEqual(future_only["grand_total"], Decimal("0.00"))

    def test_purchases_report_requires_permission_and_reconciles_totals(self):
        with self.assertRaises(PermissionDenied):
            purchases_report(actor=self.no_perms)
        report = purchases_report(actor=self.purchasing_viewer)
        self.assertEqual(report["invoice_count"], 1)
        self.assertEqual(report["grand_total"], Decimal("200.00"))

    def test_current_inventory_report_requires_permission_and_values_stock(self):
        with self.assertRaises(PermissionDenied):
            current_inventory_report(actor=self.no_perms)
        report = current_inventory_report(actor=self.inventory_viewer)
        # 3 + 2 + 1 = 6 units, each at 4.0000 acquisition cost = 24.0000
        self.assertEqual(report["total_valuation"], Decimal("24.00"))
        self.assertEqual(len(report["by_medicine"]), 1)
        self.assertEqual(report["by_medicine"][0]["quantity_on_hand_base"], Decimal("6.000"))

    def test_low_stock_report_requires_permission_and_flags_below_threshold(self):
        with self.assertRaises(PermissionDenied):
            low_stock_report(actor=self.no_perms)
        rows = low_stock_report(actor=self.inventory_viewer)
        # total on hand = 6.000, threshold = 5.000 -> at/below threshold? 6 > 5, so NOT low.
        self.assertEqual(rows, [])

    def test_low_stock_report_flags_when_below_threshold(self):
        self.low_batch.quantity_available_base = Decimal("0.000")
        self.low_batch.save(update_fields=["quantity_available_base"])
        self.near_expiry_batch.quantity_available_base = Decimal("1.000")
        self.near_expiry_batch.save(update_fields=["quantity_available_base"])
        rows = low_stock_report(actor=self.inventory_viewer)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["medicine"], self.medicine)

    def test_near_expiry_report_requires_permission_and_excludes_expired(self):
        with self.assertRaises(PermissionDenied):
            near_expiry_report(actor=self.no_perms)
        results = list(near_expiry_report(actor=self.inventory_viewer))
        self.assertEqual(results, [self.near_expiry_batch])

    def test_expired_stock_report_requires_permission_and_only_returns_expired(self):
        with self.assertRaises(PermissionDenied):
            expired_stock_report(actor=self.no_perms)
        results = list(expired_stock_report(actor=self.inventory_viewer))
        self.assertEqual(results, [self.expired_batch])


class FinancialReportPermissionTests(_ReportsFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build_fixtures()
        cls.finance_viewer = get_user_model().objects.create_user(username="finance-viewer")
        permission = Permission.objects.get(
            content_type__app_label="finance", codename="view_financial_reports"
        )
        cls.finance_viewer.user_permissions.add(permission)
        cls.no_perms = get_user_model().objects.create_user(username="no-perms-finance")

    def test_all_financial_reports_require_finance_view_financial_reports(self):
        for report_fn, kwargs in [
            (customer_receivables_report, {}),
            (supplier_payables_report, {}),
            (customer_payments_report, {}),
            (supplier_payments_report, {}),
            (cogs_and_gross_profit_report, {}),
        ]:
            with self.assertRaises(PermissionDenied):
                report_fn(actor=self.no_perms, **kwargs)

    def test_customer_receivables_report_distinguishes_invoice_and_net_balances(self):
        report = customer_receivables_report(actor=self.finance_viewer)
        # Invoice-only balance: unaffected by the posted return/refund.
        self.assertEqual(report["invoice_balance_total"], Decimal("70.00"))
        # Net statement balance: 110 - 40 - 10 + 10 = 70 as well here, but
        # computed through the separate returns/refunds-aware path.
        self.assertEqual(report["net_receivables_total"], Decimal("70.00"))
        self.assertEqual(len(report["by_customer"]), 1)
        self.assertEqual(report["by_customer"][0]["net_balance"], Decimal("70.00"))

    def test_supplier_payables_report_distinguishes_invoice_and_net_balances(self):
        report = supplier_payables_report(actor=self.finance_viewer)
        self.assertEqual(report["invoice_balance_total"], Decimal("150.00"))
        # -200 + 50 + 20 = -130 -> payable amount = 130.00
        self.assertEqual(report["net_payables_total"], Decimal("130.00"))
        self.assertEqual(report["by_supplier"][0]["payable_amount"], Decimal("130.00"))

    def test_customer_payments_report_totals(self):
        report = customer_payments_report(actor=self.finance_viewer)
        self.assertEqual(report["payment_count"], 1)
        self.assertEqual(report["amount_total"], Decimal("40.00"))

    def test_supplier_payments_report_totals(self):
        report = supplier_payments_report(actor=self.finance_viewer)
        self.assertEqual(report["payment_count"], 1)
        self.assertEqual(report["amount_total"], Decimal("50.00"))

    def test_cogs_and_gross_profit_report_uses_allocation_cost_snapshots(self):
        report = cogs_and_gross_profit_report(actor=self.finance_viewer)
        self.assertEqual(report.cogs, Decimal("42.00"))
        # revenue_excl_tax = subtotal(100.00) - discount(0.00) = 100.00
        self.assertEqual(report.revenue_excl_tax, Decimal("100.00"))
        self.assertEqual(report.gross_profit, Decimal("58.00"))
        self.assertEqual(report.invoice_count, 1)


class ReportPermissionConstantTests(TestCase):
    def test_financial_report_permission_matches_declared_codename(self):
        self.assertEqual(FINANCIAL_REPORT_PERMISSION, "finance.view_financial_reports")
