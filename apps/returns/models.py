import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class ReturnStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    POSTED = "POSTED", "Posted"
    VOID = "VOID", "Void"


class PostedStatus(models.TextChoices):
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"


class CustomerReturn(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    return_number = models.CharField(max_length=40, unique=True)
    sales_invoice = models.ForeignKey(
        "sales.SalesInvoice",
        on_delete=models.PROTECT,
        related_name="customer_returns",
    )
    customer = models.ForeignKey(
        "parties.Customer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="returns",
    )
    reason = models.TextField()
    return_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=10, choices=ReturnStatus, default=ReturnStatus.DRAFT)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="customer_returns_processed",
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "returns_customer_return"
        permissions = [("post_customerreturn", "Can post customer return")]
        constraints = [
            models.CheckConstraint(
                condition=Q(return_total__gte=0),
                name="returns_customer_total_nonnegative",
            )
        ]
        indexes = [
            models.Index(
                fields=["sales_invoice", "status"],
                name="returns_customer_invoice_idx",
            )
        ]

    def clean(self):
        super().clean()
        if self.sales_invoice_id and self.sales_invoice.customer_id != self.customer_id:
            raise ValidationError(
                {"customer": "The customer must match the original sales invoice."}
            )

    def __str__(self):
        return self.return_number


class CustomerReturnLine(models.Model):
    class Condition(models.TextChoices):
        RESALABLE = "RESALABLE", "Resalable"
        NON_RESELLABLE = "NON_RESELLABLE", "Non-resellable"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer_return = models.ForeignKey(
        CustomerReturn,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    sales_invoice_line = models.ForeignKey(
        "sales.SalesInvoiceLine",
        on_delete=models.PROTECT,
        related_name="customer_return_lines",
    )
    batch = models.ForeignKey(
        "inventory.MedicineBatch",
        on_delete=models.PROTECT,
        related_name="customer_return_lines",
    )
    returned_quantity_base = models.DecimalField(max_digits=14, decimal_places=3)
    condition = models.CharField(max_length=20, choices=Condition)
    restock = models.BooleanField(default=False)
    refund_amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "returns_customer_return_line"
        constraints = [
            models.CheckConstraint(
                condition=Q(returned_quantity_base__gt=0),
                name="returns_customer_line_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(refund_amount__gte=0),
                name="returns_customer_line_refund_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(restock=False) | Q(condition="RESALABLE"),
                name="returns_restock_requires_resalable",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.customer_return_id and self.sales_invoice_line_id:
            if (
                self.sales_invoice_line.sales_invoice_id
                != self.customer_return.sales_invoice_id
            ):
                errors["sales_invoice_line"] = (
                    "The sales line must belong to the original sales invoice."
                )
        if self.sales_invoice_line_id and self.batch_id:
            if not self.sales_invoice_line.batch_allocations.filter(batch_id=self.batch_id).exists():
                errors["batch"] = "The batch must have been allocated to the original sales line."
        if self.restock and self.condition != self.Condition.RESALABLE:
            errors["restock"] = "Only resalable items may be restocked."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.returned_quantity_base} from {self.batch_id}"


class CustomerRefund(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    refund_number = models.CharField(max_length=40, unique=True)
    customer_return = models.ForeignKey(
        CustomerReturn,
        on_delete=models.PROTECT,
        related_name="refunds",
    )
    sales_invoice = models.ForeignKey(
        "sales.SalesInvoice",
        on_delete=models.PROTECT,
        related_name="refunds",
    )
    payment_method = models.ForeignKey(
        "core.PaymentMethod",
        on_delete=models.PROTECT,
        related_name="customer_refunds",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=150, blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="customer_refunds_processed",
    )
    refunded_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=PostedStatus, default=PostedStatus.POSTED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "returns_customer_refund"
        permissions = [("process_refund", "Can process customer refund")]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="returns_customer_refund_positive",
            )
        ]
        indexes = [
            models.Index(
                fields=["customer_return", "status", "refunded_at"],
                name="returns_refund_status_idx",
            )
        ]

    def clean(self):
        super().clean()
        errors = {}
        if (
            self.customer_return_id
            and self.sales_invoice_id
            and self.customer_return.sales_invoice_id != self.sales_invoice_id
        ):
            errors["sales_invoice"] = "The invoice must match the customer return invoice."
        if self.customer_return_id and self.amount is not None:
            if self.amount > self.customer_return.return_total:
                errors["amount"] = "The refund cannot exceed the customer return total."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.refund_number


class SupplierReturn(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    return_number = models.CharField(max_length=40, unique=True)
    supplier = models.ForeignKey(
        "parties.Supplier",
        on_delete=models.PROTECT,
        related_name="returns",
    )
    purchase_invoice = models.ForeignKey(
        "purchasing.PurchaseInvoice",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="supplier_returns",
    )
    reason = models.TextField()
    return_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=10, choices=ReturnStatus, default=ReturnStatus.DRAFT)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="supplier_returns_processed",
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "returns_supplier_return"
        permissions = [("post_supplierreturn", "Can post supplier return")]
        constraints = [
            models.CheckConstraint(
                condition=Q(return_total__gte=0),
                name="returns_supplier_total_nonnegative",
            )
        ]
        indexes = [
            models.Index(
                fields=["supplier", "status"],
                name="returns_supplier_status_idx",
            )
        ]

    def clean(self):
        super().clean()
        if (
            self.purchase_invoice_id
            and self.supplier_id
            and self.purchase_invoice.supplier_id != self.supplier_id
        ):
            raise ValidationError(
                {"purchase_invoice": "The purchase invoice must belong to the supplier."}
            )

    def __str__(self):
        return self.return_number


class SupplierReturnLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier_return = models.ForeignKey(
        SupplierReturn,
        on_delete=models.PROTECT,
        related_name="lines",
    )
    medicine = models.ForeignKey(
        "catalog.Medicine",
        on_delete=models.PROTECT,
        related_name="supplier_return_lines",
    )
    batch = models.ForeignKey(
        "inventory.MedicineBatch",
        on_delete=models.PROTECT,
        related_name="supplier_return_lines",
    )
    returned_quantity_base = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost_snapshot = models.DecimalField(max_digits=14, decimal_places=4)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "returns_supplier_return_line"
        constraints = [
            models.CheckConstraint(
                condition=Q(returned_quantity_base__gt=0),
                name="returns_supplier_line_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(unit_cost_snapshot__gte=0) & Q(line_total__gte=0),
                name="returns_supplier_line_amounts_nonnegative",
            ),
        ]

    def clean(self):
        super().clean()
        if self.batch_id and self.medicine_id and self.batch.medicine_id != self.medicine_id:
            raise ValidationError({"batch": "The batch must belong to the selected medicine."})

    def __str__(self):
        return f"{self.returned_quantity_base} from {self.batch_id}"
