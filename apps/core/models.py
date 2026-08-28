import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q


class TaxRate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    rate_percent = models.DecimalField(max_digits=7, decimal_places=4)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_tax_rate"
        constraints = [
            models.CheckConstraint(
                condition=Q(rate_percent__gte=0) & Q(rate_percent__lte=100),
                name="core_tax_rate_percent_range",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.rate_percent}%)"


class PaymentMethod(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    requires_reference = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_payment_method"

    def __str__(self):
        return self.name


class PharmacySettings(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    singleton_key = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    pharmacy_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    currency_code = models.CharField(max_length=3)
    default_tax_rate = models.ForeignKey(
        TaxRate,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pharmacy_settings",
    )
    expiry_warning_days = models.PositiveIntegerField(default=90)
    default_low_stock_threshold = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        default=Decimal("0.000"),
    )
    invoice_header = models.TextField(blank=True)
    invoice_footer = models.TextField(blank=True)
    receipt_footer = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_pharmacy_settings"
        verbose_name_plural = "pharmacy settings"
        constraints = [
            models.CheckConstraint(
                condition=Q(singleton_key=1),
                name="core_pharmacy_settings_singleton",
            ),
            models.CheckConstraint(
                condition=Q(default_low_stock_threshold__gte=0),
                name="core_pharmacy_settings_low_stock_nonnegative",
            ),
        ]

    def __str__(self):
        return self.pharmacy_name
