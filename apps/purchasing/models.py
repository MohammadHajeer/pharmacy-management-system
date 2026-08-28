import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q


class PurchaseInvoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        POSTED = "POSTED", "Posted"
        VOID = "VOID", "Void"

    class PaymentStatus(models.TextChoices):
        UNPAID = "UNPAID", "Unpaid"
        PARTIAL = "PARTIAL", "Partially paid"
        PAID = "PAID", "Paid"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=40, blank=True, default="")
    supplier_invoice_reference = models.CharField(max_length=100, blank=True)
    supplier = models.ForeignKey(
        "parties.Supplier",
        on_delete=models.PROTECT,
        related_name="purchase_invoices",
    )
    invoice_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status, default=Status.DRAFT)
    payment_status = models.CharField(
        max_length=10,
        choices=PaymentStatus,
        default=PaymentStatus.UNPAID,
    )
    supplier_name_snapshot = models.CharField(max_length=200, blank=True)
    pharmacy_name_snapshot = models.CharField(max_length=200, blank=True)
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
    remaining_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="purchase_invoices_created",
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_invoices_posted",
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "purchasing_purchase_invoice"
        permissions = [("post_purchaseinvoice", "Can post purchase invoice")]
        constraints = [
            models.UniqueConstraint(
                fields=["invoice_number"],
                condition=Q(status="POSTED"),
                name="purchasing_posted_invoice_number_unique",
            ),
            models.CheckConstraint(
                condition=~Q(status="POSTED") | ~Q(invoice_number=""),
                name="purchasing_posted_invoice_has_number",
            ),
            models.CheckConstraint(
                condition=Q(subtotal__gte=0)
                & Q(discount_total__gte=0)
                & Q(tax_total__gte=0)
                & Q(grand_total__gte=0)
                & Q(paid_total__gte=0)
                & Q(remaining_balance__gte=0),
                name="purchasing_invoice_totals_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(remaining_balance=F("grand_total") - F("paid_total")),
                name="purchasing_invoice_balance_matches",
            ),
        ]
        indexes = [
            models.Index(
                fields=["supplier", "invoice_date"],
                name="purchasing_supplier_date_idx",
            ),
            models.Index(
                fields=["status", "payment_status"],
                name="purchasing_status_payment_idx",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.status == self.Status.POSTED and not self.invoice_number:
            errors["invoice_number"] = "A posted purchase invoice requires an invoice number."
        if self.status == self.Status.POSTED and not self._state.adding and not self.lines.exists():
            errors["status"] = "A posted purchase invoice requires at least one line."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.invoice_number or f"Draft purchase {self.id}"


class PurchaseInvoiceLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_invoice = models.ForeignKey(
        PurchaseInvoice,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    medicine = models.ForeignKey(
        "catalog.Medicine",
        on_delete=models.PROTECT,
        related_name="purchase_invoice_lines",
    )
    medicine_description_snapshot = models.CharField(max_length=240)
    medicine_unit = models.ForeignKey(
        "catalog.MedicineUnit",
        on_delete=models.PROTECT,
        related_name="purchase_invoice_lines",
    )
    unit_name_snapshot = models.CharField(max_length=80)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    conversion_to_base_snapshot = models.DecimalField(max_digits=14, decimal_places=6)
    received_quantity_base = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4)
    discount_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    tax_rate_percent = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    batch_number = models.CharField(max_length=100)
    expiry_date = models.DateField()
    medicine_batch = models.ForeignKey(
        "inventory.MedicineBatch",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_invoice_lines",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "purchasing_purchase_invoice_line"
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="purchasing_line_quantity_positive"),
            models.CheckConstraint(
                condition=Q(conversion_to_base_snapshot__gt=0),
                name="purchasing_line_conversion_positive",
            ),
            models.CheckConstraint(
                condition=Q(received_quantity_base__gt=0),
                name="purchasing_line_received_positive",
            ),
            models.CheckConstraint(
                condition=Q(unit_cost__gte=0)
                & Q(discount_amount__gte=0)
                & Q(tax_rate_percent__gte=0)
                & Q(tax_rate_percent__lte=100)
                & Q(tax_amount__gte=0)
                & Q(line_total__gte=0),
                name="purchasing_line_amounts_valid",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.medicine_unit_id and self.medicine_id:
            if self.medicine_unit.medicine_id != self.medicine_id:
                errors["medicine_unit"] = "The unit must belong to the selected medicine."
            elif not self.medicine_unit.purchase_allowed:
                errors["medicine_unit"] = "The selected unit is not allowed for purchases."
        if (
            self.quantity is not None
            and self.conversion_to_base_snapshot is not None
            and self.received_quantity_base
            != self.quantity * self.conversion_to_base_snapshot
        ):
            errors["received_quantity_base"] = (
                "Received base quantity must equal quantity multiplied by the conversion snapshot."
            )
        if self.medicine_batch_id:
            if self.medicine_batch.medicine_id != self.medicine_id:
                errors["medicine_batch"] = "The batch must belong to the selected medicine."
            elif (
                self.medicine_batch.batch_number != self.batch_number
                or self.medicine_batch.expiry_date != self.expiry_date
            ):
                errors["medicine_batch"] = "The batch number and expiry must match the line snapshots."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.medicine_description_snapshot} × {self.quantity}"
