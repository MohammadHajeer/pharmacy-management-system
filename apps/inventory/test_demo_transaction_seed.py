"""Focused tests for the isolated V2 transactional development seed."""

from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.db.models import Count, Sum
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.catalog.models import Medicine
from apps.core.models import PaymentMethod, PharmacySettings
from apps.finance.models import CustomerPayment, PaymentStatus, SupplierPayment
from apps.inventory.management.demo_dataset import identity as base_identity
from apps.inventory.management.transaction_demo_dataset import (
    COMPLETED_SALE_COUNT,
    CUSTOMER_COUNT,
    DRAFT_SALE_COUNT,
    PRESCRIBER_COUNT,
    PRESCRIPTION_COUNT,
    PRESCRIPTION_ITEMS_PER_RECORD,
    transaction_identity,
)
from apps.inventory.models import MedicineBatch, StockMovement
from apps.parties.models import Customer, Prescriber
from apps.prescriptions.models import Prescription, PrescriptionItem
from apps.purchasing.models import PurchaseInvoice
from apps.sales.models import SaleBatchAllocation, SalesInvoice, SalesInvoiceLine
from apps.returns.models import (
    CustomerRefund,
    CustomerReturn,
    CustomerReturnLine,
    SupplierReturn,
    SupplierReturnLine,
)


def run_command(name):
    output = StringIO()
    call_command(name, stdout=output, stderr=StringIO())
    return output.getvalue()


def stock_state():
    today = timezone.localdate()
    pharmacy = PharmacySettings.objects.get(singleton_key=1)
    result = {"healthy": 0, "low": 0, "no_sellable": 0}
    for medicine in Medicine.objects.filter(is_active=True).prefetch_related("batches"):
        quantity = sum(
            (
                batch.quantity_available_base
                for batch in medicine.batches.all()
                if batch.is_active and batch.expiry_date >= today
            ),
            Decimal("0.000"),
        )
        threshold = medicine.low_stock_threshold_base or pharmacy.default_low_stock_threshold
        key = "no_sellable" if quantity == 0 else "low" if quantity <= threshold else "healthy"
        result[key] += 1
    return result


@override_settings(DEBUG=True)
class TransactionDemoSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = get_user_model().objects.create_user(username="owner")
        cls.actor.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label__in=("sales", "finance"),
                codename__in=(
                    "change_salesinvoice",
                    "change_salesinvoiceline",
                    "complete_sale",
                    "post_customerpayment",
                    "post_supplierpayment",
                ),
            )
        )
        PharmacySettings.objects.create(
            pharmacy_name="Shared development pharmacy",
            currency_code="USD",
        )
        PaymentMethod.objects.create(
            code="DEMO-CASH",
            name="Demo Cash",
            requires_reference=False,
        )
        run_command("seed_demo_data")
        cls.before_stock_state = stock_state()
        cls.before_expiry = cls._expiry_counts()
        cls.output = run_command("seed_demo_transactions")

    @staticmethod
    def _expiry_counts():
        today = timezone.localdate()
        return (
            MedicineBatch.objects.filter(expiry_date__lt=today).count(),
            MedicineBatch.objects.filter(
                expiry_date__range=(today, today + timedelta(days=30))
            ).count(),
            MedicineBatch.objects.filter(
                expiry_date__range=(today + timedelta(days=31), today + timedelta(days=90))
            ).count(),
        )

    def test_target_counts_and_distributions(self):
        self.assertEqual(Customer.objects.count(), CUSTOMER_COUNT)
        self.assertEqual(Prescriber.objects.count(), PRESCRIBER_COUNT)
        self.assertEqual(Prescription.objects.count(), PRESCRIPTION_COUNT)
        self.assertEqual(
            PrescriptionItem.objects.count(),
            PRESCRIPTION_COUNT * PRESCRIPTION_ITEMS_PER_RECORD,
        )
        self.assertEqual(SalesInvoice.objects.count(), COMPLETED_SALE_COUNT + DRAFT_SALE_COUNT)
        self.assertEqual(SalesInvoice.objects.filter(status="COMPLETED").count(), 84)
        self.assertEqual(SalesInvoice.objects.filter(status="DRAFT").count(), 4)
        self.assertEqual(SalesInvoiceLine.objects.count(), 175)
        self.assertGreaterEqual(SaleBatchAllocation.objects.count(), 171)
        self.assertEqual(
            list(
                SalesInvoice.objects.filter(status="COMPLETED")
                .values_list("payment_status")
                .annotate(count=Count("pk"))
                .order_by("payment_status")
            ),
            [("PAID", 56), ("PARTIAL", 14), ("UNPAID", 14)],
        )
        self.assertEqual(
            SalesInvoice.objects.filter(status="COMPLETED", customer__isnull=True).count(),
            36,
        )
        self.assertEqual(
            SalesInvoice.objects.filter(status="COMPLETED", prescription__isnull=False).count(),
            20,
        )
        self.assertIn("PHARMANEX transactional demo data ready", self.output)

    def test_payment_balances_reversals_and_supplier_scenarios(self):
        self.assertEqual(CustomerPayment.objects.filter(status=PaymentStatus.POSTED).count(), 70)
        self.assertEqual(CustomerPayment.objects.filter(status=PaymentStatus.REVERSED).count(), 3)
        self.assertEqual(SupplierPayment.objects.filter(status=PaymentStatus.POSTED).count(), 14)
        self.assertEqual(SupplierPayment.objects.filter(status=PaymentStatus.REVERSED).count(), 2)
        for invoice in SalesInvoice.objects.filter(status="COMPLETED").prefetch_related(
            "payments"
        ):
            total = invoice.payments.filter(status=PaymentStatus.POSTED).aggregate(
                total=Sum("amount")
            )["total"] or Decimal("0.00")
            self.assertEqual(invoice.paid_total, total)
            self.assertEqual(invoice.balance_due, invoice.grand_total - total)
            self.assertLessEqual(total, invoice.grand_total)
            if invoice.customer_id is None:
                self.assertEqual(invoice.balance_due, Decimal("0.00"))
        self.assertEqual(PurchaseInvoice.objects.filter(payment_status="PAID").count(), 8)
        self.assertEqual(PurchaseInvoice.objects.filter(payment_status="PARTIAL").count(), 6)
        self.assertEqual(PurchaseInvoice.objects.filter(payment_status="UNPAID").count(), 9)

    def test_fefo_allocations_sale_movements_and_stock_reconcile(self):
        self.assertEqual(
            SaleBatchAllocation.objects.count(),
            StockMovement.objects.filter(movement_type="SALE").count(),
        )
        self.assertGreaterEqual(
            SalesInvoiceLine.objects.annotate(n=Count("batch_allocations"))
            .filter(n__gt=1)
            .count(),
            3,
        )
        for allocation in SaleBatchAllocation.objects.select_related(
            "sales_invoice_line", "batch"
        ):
            movement = StockMovement.objects.get(
                movement_type="SALE",
                source_id=allocation.sales_invoice_line.sales_invoice_id,
                source_line_id=allocation.pk,
            )
            self.assertEqual(movement.source_type, "SALE")
            self.assertEqual(movement.batch_id, allocation.batch_id)
            self.assertEqual(movement.quantity_delta_base, -allocation.allocated_quantity_base)
        for batch in MedicineBatch.objects.all():
            self.assertGreaterEqual(batch.quantity_available_base, 0)
            self.assertEqual(
                batch.quantity_available_base,
                batch.stock_movements.aggregate(total=Sum("quantity_delta_base"))["total"],
            )

    def test_prescription_links_and_historical_activity(self):
        for invoice in SalesInvoice.objects.filter(prescription__isnull=False).select_related(
            "prescription"
        ):
            self.assertEqual(invoice.customer_id, invoice.prescription.customer_id)
            self.assertTrue(
                invoice.lines.filter(
                    medicine_id__in=invoice.prescription.items.values("medicine_id")
                ).exists()
            )
        self.assertTrue(
            SalesInvoiceLine.objects.filter(prescription_required_snapshot=True).exists()
        )
        dates = list(
            SalesInvoice.objects.filter(status="COMPLETED").values_list(
                "completed_at", flat=True
            )
        )
        self.assertGreater((max(dates) - min(dates)).days, 180)
        for allocation in SaleBatchAllocation.objects.select_related(
            "sales_invoice_line__sales_invoice", "batch"
        ):
            self.assertLessEqual(
                allocation.batch.first_received_at,
                allocation.sales_invoice_line.sales_invoice.completed_at,
            )

    def test_original_inventory_scenarios_and_returns_scope_are_preserved(self):
        self.assertEqual(stock_state(), self.before_stock_state)
        self.assertEqual(self._expiry_counts(), self.before_expiry)
        self.assertTrue(all(self.before_stock_state.values()))
        self.assertEqual(
            tuple(
                model.objects.count()
                for model in (
                    CustomerReturn,
                    CustomerReturnLine,
                    CustomerRefund,
                    SupplierReturn,
                    SupplierReturnLine,
                )
            ),
            (0, 0, 0, 0, 0),
        )

    def test_rerun_is_read_only_and_does_not_duplicate_or_replenish(self):
        models = (
            Customer,
            Prescriber,
            Prescription,
            PrescriptionItem,
            SalesInvoice,
            SalesInvoiceLine,
            SaleBatchAllocation,
            CustomerPayment,
            SupplierPayment,
            MedicineBatch,
            StockMovement,
        )
        before = {model: list(model.objects.order_by("pk").values()) for model in models}
        output = run_command("seed_demo_transactions")
        self.assertIn("creation skipped", output)
        self.assertIn("Existing V2 records preserved", output)
        for model in models:
            self.assertEqual(list(model.objects.order_by("pk").values()), before[model])

    def test_deterministic_document_identities(self):
        for index in range(COMPLETED_SALE_COUNT + DRAFT_SALE_COUNT):
            invoice = SalesInvoice.objects.get(pk=transaction_identity("sale", index))
            if index < COMPLETED_SALE_COUNT:
                self.assertTrue(invoice.invoice_number.startswith("SAL-"))
            else:
                self.assertEqual(invoice.invoice_number, "")
        self.assertEqual(
            PurchaseInvoice.objects.filter(
                pk__in=[base_identity("invoice", index) for index in range(23)]
            ).count(),
            23,
        )
