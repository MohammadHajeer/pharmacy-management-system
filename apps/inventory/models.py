import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class MedicineBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medicine = models.ForeignKey(
        "catalog.Medicine",
        on_delete=models.PROTECT,
        related_name="batches",
    )
    batch_number = models.CharField(max_length=100)
    expiry_date = models.DateField()
    acquisition_cost_per_base_unit = models.DecimalField(
        max_digits=14,
        decimal_places=4,
    )
    quantity_available_base = models.DecimalField(max_digits=14, decimal_places=3)
    first_received_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "inventory_medicine_batch"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "medicine",
                    "batch_number",
                    "expiry_date",
                    "acquisition_cost_per_base_unit",
                ],
                name="inventory_batch_cost_layer_unique",
            ),
            models.CheckConstraint(
                condition=Q(acquisition_cost_per_base_unit__gte=0),
                name="inventory_batch_cost_nonnegative",
            ),
            models.CheckConstraint(
                condition=Q(quantity_available_base__gte=0),
                name="inventory_batch_quantity_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["medicine", "is_active", "expiry_date", "first_received_at"],
                name="inventory_batch_fefo_idx",
            ),
            models.Index(
                fields=["expiry_date", "is_active"],
                name="inventory_batch_expiry_idx",
            ),
        ]

    def __str__(self):
        return f"{self.batch_number} — {self.medicine_id}"


class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        PURCHASE_RECEIPT = "PURCHASE_RECEIPT", "Purchase receipt"
        SALE = "SALE", "Sale"
        CUSTOMER_RETURN_RESTOCK = "CUSTOMER_RETURN_RESTOCK", "Customer return restock"
        SUPPLIER_RETURN = "SUPPLIER_RETURN", "Supplier return"
        MANUAL_ADJUSTMENT_IN = "MANUAL_ADJUSTMENT_IN", "Manual adjustment in"
        MANUAL_ADJUSTMENT_OUT = "MANUAL_ADJUSTMENT_OUT", "Manual adjustment out"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    medicine = models.ForeignKey(
        "catalog.Medicine",
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    batch = models.ForeignKey(
        MedicineBatch,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    movement_type = models.CharField(max_length=32, choices=MovementType)
    quantity_delta_base = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost_snapshot = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )
    source_type = models.CharField(max_length=40)
    source_id = models.UUIDField()
    source_line_id = models.UUIDField(null=True, blank=True)
    reference_number = models.CharField(max_length=80, blank=True)
    reason = models.TextField(blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stock_movements_performed",
    )
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_stock_movement"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "movement_type",
                    "source_type",
                    "source_id",
                    "source_line_id",
                ],
                condition=Q(source_line_id__isnull=False),
                name="inventory_movement_source_line_unique",
            ),
            models.CheckConstraint(
                condition=~Q(quantity_delta_base=0),
                name="inventory_movement_delta_nonzero",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        movement_type__in=[
                            "PURCHASE_RECEIPT",
                            "CUSTOMER_RETURN_RESTOCK",
                            "MANUAL_ADJUSTMENT_IN",
                        ],
                        quantity_delta_base__gt=0,
                    )
                    | Q(
                        movement_type__in=[
                            "SALE",
                            "SUPPLIER_RETURN",
                            "MANUAL_ADJUSTMENT_OUT",
                        ],
                        quantity_delta_base__lt=0,
                    )
                ),
                name="inventory_movement_delta_direction",
            ),
            models.CheckConstraint(
                condition=Q(unit_cost_snapshot__isnull=True) | Q(unit_cost_snapshot__gte=0),
                name="inventory_movement_cost_nonnegative",
            ),
        ]
        indexes = [
            models.Index(
                fields=["batch", "occurred_at"],
                name="inventory_move_batch_time_idx",
            ),
            models.Index(
                fields=["source_type", "source_id"],
                name="inventory_move_source_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if self.batch_id and self.medicine_id and self.batch.medicine_id != self.medicine_id:
            raise ValidationError({"batch": "The batch must belong to the selected medicine."})

    def __str__(self):
        return f"{self.movement_type}: {self.quantity_delta_base}"
