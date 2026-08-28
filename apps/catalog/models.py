import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_category"
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="catalog_category_name_ci_unique",
            )
        ]

    def __str__(self):
        return self.name


class Manufacturer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_manufacturer"

    def __str__(self):
        return self.name


class Medicine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    generic_name = models.CharField(max_length=200, blank=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="medicines",
    )
    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.PROTECT,
        related_name="medicines",
    )
    strength = models.CharField(max_length=100, blank=True)
    dosage_form = models.CharField(max_length=100, blank=True)
    prescription_required = models.BooleanField(default=False)
    low_stock_threshold_base = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
    )
    default_selling_price = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_medicine"
        constraints = [
            models.CheckConstraint(
                condition=Q(low_stock_threshold_base__isnull=True)
                | Q(low_stock_threshold_base__gte=0),
                name="catalog_medicine_low_stock_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(default_selling_price__gte=0),
                name="catalog_medicine_price_nonnegative",
            ),
        ]
        indexes = [
            models.Index(fields=["name"], name="catalog_med_name_idx"),
            models.Index(fields=["is_active"], name="catalog_med_active_idx"),
        ]

    def __str__(self):
        return self.name


class MedicineUnit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.PROTECT,
        related_name="units",
    )
    name = models.CharField(max_length=80)
    conversion_to_base = models.DecimalField(max_digits=14, decimal_places=6)
    is_base_unit = models.BooleanField(default=False)
    purchase_allowed = models.BooleanField(default=True)
    sale_allowed = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_medicine_unit"
        constraints = [
            models.UniqueConstraint(
                fields=["medicine", "name"],
                name="catalog_unit_medicine_name_unique",
            ),
            models.UniqueConstraint(
                fields=["medicine"],
                condition=Q(is_base_unit=True, is_active=True),
                name="catalog_unit_one_active_base",
            ),
            models.CheckConstraint(
                condition=Q(conversion_to_base__gt=0),
                name="catalog_unit_conversion_positive",
            ),
            models.CheckConstraint(
                condition=Q(is_base_unit=False) | Q(conversion_to_base=Decimal("1.000000")),
                name="catalog_unit_base_conversion_one",
            ),
        ]

    def clean(self):
        super().clean()
        if self.is_base_unit and self.conversion_to_base != Decimal("1"):
            raise ValidationError(
                {"conversion_to_base": "A base unit must have a conversion factor of 1."}
            )

    def __str__(self):
        return f"{self.medicine_id}: {self.name}"


class MedicineBarcode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medicine_unit = models.ForeignKey(
        MedicineUnit,
        on_delete=models.PROTECT,
        related_name="barcodes",
    )
    barcode = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_medicine_barcode"

    def __str__(self):
        return self.barcode
