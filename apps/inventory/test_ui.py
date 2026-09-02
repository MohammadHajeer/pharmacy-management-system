import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Manufacturer, Medicine

from .models import MedicineBatch, StockMovement


class InventoryUITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.viewer = user_model.objects.create_user(username="inventory-viewer")
        cls.snapshot_viewer = user_model.objects.create_user(username="inventory-snapshot")
        cls.unauthorized = user_model.objects.create_user(username="inventory-denied")
        cls.viewer.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="inventory",
                codename__in={"view_medicinebatch", "view_stockmovement"},
            )
        )
        cls.snapshot_viewer.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="inventory", codename="view_medicinebatch"
            )
        )
        category = Category.objects.create(name="Inventory UI")
        manufacturer = Manufacturer.objects.create(name="Inventory Labs")
        cls.medicine = Medicine.objects.create(
            name="Amoxicillin UI",
            category=category,
            manufacturer=manufacturer,
            low_stock_threshold_base=Decimal("10.000"),
        )
        cls.batch = MedicineBatch.objects.create(
            medicine=cls.medicine,
            batch_number="LOT-UI-001",
            expiry_date=timezone.localdate() + timedelta(days=20),
            acquisition_cost_per_base_unit=Decimal("1.2500"),
            quantity_available_base=Decimal("5.000"),
            first_received_at=timezone.now(),
        )
        cls.movement = StockMovement.objects.create(
            medicine=cls.medicine,
            batch=cls.batch,
            movement_type=StockMovement.MovementType.PURCHASE_RECEIPT,
            quantity_delta_base=Decimal("5.000"),
            unit_cost_snapshot=Decimal("1.2500"),
            source_type="PURCHASE_RECEIPT",
            source_id=uuid.uuid4(),
            reference_number="PUR-UI-001",
            performed_by=cls.viewer,
            occurred_at=timezone.now(),
        )

    def test_registry_requires_permission_and_renders_low_expiry_context(self):
        response = self.client.get(reverse("inventory:batch-list"))
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.unauthorized)
        self.assertEqual(self.client.get(reverse("inventory:batch-list")).status_code, 403)
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("inventory:batch-list"), {"q": "Amoxicillin"})
        self.assertContains(response, "LOT-UI-001")
        self.assertContains(response, "Near expiry")
        self.assertContains(response, "Quantities are read-only here")

    def test_filters_and_pagination_are_server_side(self):
        for index in range(25):
            MedicineBatch.objects.create(
                medicine=self.medicine,
                batch_number=f"LOT-UI-{index + 100:03d}",
                expiry_date=timezone.localdate() + timedelta(days=200 + index),
                acquisition_cost_per_base_unit=Decimal("1.2500"),
                quantity_available_base=Decimal("1.000"),
                first_received_at=timezone.now(),
            )
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("inventory:batch-list"), {"page": 2})
        self.assertEqual(response.context["page_obj"].number, 2)
        response = self.client.get(reverse("inventory:batch-list"), {"status": "expired"})
        self.assertEqual(list(response.context["batches"]), [])

    def test_batch_detail_scopes_movement_history_by_permission(self):
        self.client.force_login(self.snapshot_viewer)
        response = self.client.get(reverse("inventory:batch-detail", args=[self.batch.pk]))
        self.assertContains(response, "Movement history is restricted")
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("inventory:batch-detail", args=[self.batch.pk]))
        self.assertContains(response, "PUR-UI-001")
        response = self.client.get(reverse("inventory:movement-list"), {"q": "PUR-UI"})
        self.assertContains(response, "Purchase receipt")
