import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Prescription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference_number = models.CharField(max_length=80, blank=True)
    customer = models.ForeignKey(
        "parties.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prescriptions",
    )
    prescriber = models.ForeignKey(
        "parties.Prescriber",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prescriptions",
    )
    prescription_date = models.DateField()
    notes = models.TextField(blank=True)
    attachment = models.FileField(upload_to="prescriptions/", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="prescriptions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "prescriptions_prescription"
        indexes = [
            models.Index(
                fields=["prescription_date"],
                name="prescriptions_date_idx",
            )
        ]

    def __str__(self):
        return self.reference_number or f"Prescription {self.id}"


class PrescriptionItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="items",
    )
    medicine = models.ForeignKey(
        "catalog.Medicine",
        on_delete=models.PROTECT,
        related_name="prescription_items",
    )
    quantity_prescribed = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
    )
    dosage_instructions = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "prescriptions_prescription_item"
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity_prescribed__isnull=True) | Q(quantity_prescribed__gt=0),
                name="prescriptions_item_quantity_positive",
            )
        ]

    def __str__(self):
        return f"{self.medicine_id} — {self.quantity_prescribed or 'unspecified'}"
