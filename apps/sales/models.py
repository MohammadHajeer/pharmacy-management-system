import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from apps.catalog.unit_economics import base_quantity


class SalesInvoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        COMPLETED = "COMPLETED", "Completed"
        VOID = "VOID", "Void"

    class PaymentStatus(models.TextChoices):
        UNPAID = "UNPAID", "Unpaid"
        PARTIAL = "PARTIAL", "Partially paid"
        PAID = "PAID", "Paid"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=40, blank=True, default="")
    status = models.CharField(max_length=10, choices=Status, default=Status.DRAFT)
    customer = models.ForeignKey(
        "parties.Customer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_invoices",
    )
    prescription = models.ForeignKey(
        "prescriptions.Prescription",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_invoices",
    )
    pharmacist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sales_invoices",
    )
    pharmacy_name_snapshot = models.CharField(max_length=200, blank=True)
    customer_name_snapshot = models.CharField(max_length=200, blank=True)
    customer_phone_snapshot = models.CharField(max_length=32, blank=True)
    currency_code = models.CharField(max_length=3)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    discount_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    paid_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    balance_due = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    payment_status = models.CharField(
        max_length=10,
        choices=PaymentStatus,
        default=PaymentStatus.UNPAID,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sales_sales_invoice"
        permissions = [("complete_sale", "Can complete sale")]
        constraints = [
            models.UniqueConstraint(
                fields=["invoice_number"],
                condition=Q(status="COMPLETED"),
                name="sales_completed_invoice_number_unique",
            ),
            models.CheckConstraint(
                condition=~Q(status="COMPLETED") | ~Q(invoice_number=""),
                name="sales_completed_invoice_has_number",
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0)
                & Q(discount_total__gte=0)
                & Q(tax_total__gte=0)
                & Q(grand_total__gte=0)
                & Q(paid_total__gte=0)
                & Q(balance_due__gte=0),
                name="sales_invoice_totals_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(balance_due=F("grand_total") - F("paid_total")),
                name="sales_invoice_balance_matches",
            ),
            models.CheckConstraint(
                condition=~Q(status="COMPLETED", customer__isnull=True) | Q(balance_due=0),
                name="sales_walkin_completed_settled",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "completed_at"],
                name="sales_status_completed_idx",
            ),
            models.Index(
                fields=["customer", "payment_status"],
                name="sales_customer_payment_idx",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.status == self.Status.COMPLETED and not self.invoice_number:
            errors["invoice_number"] = "A completed sale requires an invoice number."
        if self.status == self.Status.COMPLETED and self.customer_id is None and self.balance_due != 0:
            errors["balance_due"] = "A completed walk-in sale must be fully settled."
        if self.status == self.Status.COMPLETED and not self._state.adding and not self.lines.exists():
            errors["status"] = "A completed sale requires at least one line."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.invoice_number or f"Draft sale {self.id}"


class SalesInvoiceLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sales_invoice = models.ForeignKey(
        SalesInvoice,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    medicine = models.ForeignKey(
        "catalog.Medicine",
        on_delete=models.PROTECT,
        related_name="sales_invoice_lines",
    )
    medicine_description_snapshot = models.CharField(max_length=240)
    medicine_unit = models.ForeignKey(
        "catalog.MedicineUnit",
        on_delete=models.PROTECT,
        related_name="sales_invoice_lines",
    )
    unit_name_snapshot = models.CharField(max_length=80)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    conversion_to_base_snapshot = models.DecimalField(max_digits=14, decimal_places=6)
    requested_quantity_base = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tax_rate_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    prescription_required_snapshot = models.BooleanField(default=False)
    prescription_warning_acknowledged = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sales_sales_invoice_line"
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sales_line_quantity_positive"),
            models.CheckConstraint(
                condition=Q(conversion_to_base_snapshot__gt=0),
                name="sales_line_conversion_positive",
            ),
            models.CheckConstraint(
                condition=Q(requested_quantity_base__gt=0),
                name="sales_line_requested_base_positive",
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0)
                & Q(discount_amount__gte=0)
                & Q(tax_rate_percent__gte=0)
                & Q(tax_rate_percent__lte=100)
                & Q(tax_amount__gte=0)
                & Q(line_total__gte=0),
                name="sales_line_amounts_valid",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.medicine_unit_id and self.medicine_id:
            if self.medicine_unit.medicine_id != self.medicine_id:
                errors["medicine_unit"] = "The unit must belong to the selected medicine."
            elif not self.medicine_unit.sale_allowed:
                errors["medicine_unit"] = "The selected unit is not allowed for sales."
        if (
            self.quantity is not None
            and self.conversion_to_base_snapshot is not None
            and self.conversion_to_base_snapshot > 0
            and self.requested_quantity_base
            != base_quantity(self.quantity, self.conversion_to_base_snapshot)
        ):
            errors["requested_quantity_base"] = (
                "Requested base quantity must equal the selected quantity multiplied by "
                "the conversion snapshot and rounded to three decimal places."
            )
        if (
            self.sales_invoice_id
            and self.sales_invoice.status == SalesInvoice.Status.COMPLETED
            and self.prescription_required_snapshot
            and not self.prescription_warning_acknowledged
        ):
            errors["prescription_warning_acknowledged"] = (
                "The prescription warning must be acknowledged before sale completion."
            )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.medicine_description_snapshot} × {self.quantity}"


class SaleBatchAllocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sales_invoice_line = models.ForeignKey(
        SalesInvoiceLine,
        on_delete=models.PROTECT,
        related_name="batch_allocations",
    )
    batch = models.ForeignKey(
        "inventory.MedicineBatch",
        on_delete=models.PROTECT,
        related_name="sale_allocations",
    )
    allocated_quantity_base = models.DecimalField(max_digits=14, decimal_places=3)
    acquisition_cost_snapshot = models.DecimalField(max_digits=14, decimal_places=4)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sales_sale_batch_allocation"
        constraints = [
            models.UniqueConstraint(
                fields=["sales_invoice_line", "batch"],
                name="sales_allocation_line_batch_unique",
            ),
            models.CheckConstraint(
                condition=Q(allocated_quantity_base__gt=0),
                name="sales_allocation_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(acquisition_cost_snapshot__gte=0),
                name="sales_allocation_cost_nonnegative",
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.batch_id
            and self.sales_invoice_line_id
            and self.batch.medicine_id != self.sales_invoice_line.medicine_id
        ):
            raise ValidationError({"batch": "The batch must belong to the line medicine."})

    def __str__(self):
        return f"{self.allocated_quantity_base} from {self.batch_id}"
