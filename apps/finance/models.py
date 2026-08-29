import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class PaymentStatus(models.TextChoices):
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"


class CustomerPayment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sales_invoice = models.ForeignKey(
        "sales.SalesInvoice",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    customer = models.ForeignKey(
        "parties.Customer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments",
    )
    payment_method = models.ForeignKey(
        "core.PaymentMethod",
        on_delete=models.PROTECT,
        related_name="customer_payments",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=150, blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="customer_payments_processed",
    )
    paid_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=PaymentStatus, default=PaymentStatus.POSTED)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="customer_payments_reversed",
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "finance_customer_payment"
        permissions = [
            ("post_customerpayment", "Can post customer payment"),
            ("view_financial_reports", "Can view financial reports"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="finance_customer_payment_positive",
            )
        ]
        indexes = [
            models.Index(
                fields=["sales_invoice", "status", "paid_at"],
                name="finance_customer_invoice_idx",
            )
        ]

    def clean(self):
        super().clean()
        if (
            self.sales_invoice_id
            and self.customer_id
            and self.sales_invoice.customer_id != self.customer_id
        ):
            raise ValidationError(
                {"customer": "The customer must match the sales invoice customer."}
            )

    def __str__(self):
        return f"{self.amount} for {self.sales_invoice_id}"


class SupplierPayment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_invoice = models.ForeignKey(
        "purchasing.PurchaseInvoice",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    supplier = models.ForeignKey(
        "parties.Supplier",
        on_delete=models.PROTECT,
        related_name="payments",
    )
    payment_method = models.ForeignKey(
        "core.PaymentMethod",
        on_delete=models.PROTECT,
        related_name="supplier_payments",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=150, blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="supplier_payments_processed",
    )
    paid_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=PaymentStatus, default=PaymentStatus.POSTED)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="supplier_payments_reversed",
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversal_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "finance_supplier_payment"
        permissions = [("post_supplierpayment", "Can post supplier payment")]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="finance_supplier_payment_positive",
            )
        ]
        indexes = [
            models.Index(
                fields=["purchase_invoice", "status", "paid_at"],
                name="finance_supplier_invoice_idx",
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
                {"supplier": "The supplier must match the purchase invoice supplier."}
            )

    def __str__(self):
        return f"{self.amount} for {self.purchase_invoice_id}"
