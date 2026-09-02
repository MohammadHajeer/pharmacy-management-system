from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Manufacturer, Medicine
from apps.parties.models import Customer, Prescriber

from .models import Prescription, PrescriptionItem


class PrescriptionUITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.user = user_model.objects.create_user(username="prescription-ui")
        cls.denied = user_model.objects.create_user(username="prescription-ui-denied")
        cls.user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="prescriptions",
                codename__in={
                    "add_prescription", "change_prescription", "view_prescription",
                    "add_prescriptionitem", "change_prescriptionitem", "view_prescriptionitem",
                },
            )
        )
        category = Category.objects.create(name="Prescription UI")
        manufacturer = Manufacturer.objects.create(name="Clinical Labs")
        cls.medicine = Medicine.objects.create(
            name="Clinical Medicine",
            category=category,
            manufacturer=manufacturer,
        )
        cls.customer = Customer.objects.create(code="CUS-UI-RX", name="Patient UI")
        cls.prescriber = Prescriber.objects.create(name="Dr UI")
        cls.prescription = Prescription.objects.create(
            reference_number="RX-UI-001",
            customer=cls.customer,
            prescriber=cls.prescriber,
            prescription_date=date(2026, 9, 1),
            created_by=cls.user,
        )
        cls.item = PrescriptionItem.objects.create(
            prescription=cls.prescription,
            medicine=cls.medicine,
            quantity_prescribed=Decimal("2.000"),
            dosage_instructions="Twice daily",
        )

    def test_registry_detail_and_search_render_real_templates(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("prescriptions:list"), {"q": "Clinical"})
        self.assertContains(response, "RX-UI-001")
        self.assertContains(response, "Patient UI")
        response = self.client.get(reverse("prescriptions:detail", args=[self.prescription.pk]))
        self.assertContains(response, "Twice daily")
        self.assertContains(response, "Edit prescription")

    def test_update_uses_existing_atomic_service(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("prescriptions:update", args=[self.prescription.pk]),
            {
                "reference_number": "RX-UI-UPDATED",
                "customer": str(self.customer.pk),
                "prescriber": str(self.prescriber.pk),
                "prescription_date": "2026-09-02",
                "notes": "Updated note",
                "items-TOTAL_FORMS": "1",
                "items-INITIAL_FORMS": "1",
                "items-MIN_NUM_FORMS": "1",
                "items-MAX_NUM_FORMS": "1000",
                "items-0-id": str(self.item.pk),
                "items-0-prescription": str(self.prescription.pk),
                "items-0-medicine": str(self.medicine.pk),
                "items-0-quantity_prescribed": "3.000",
                "items-0-dosage_instructions": "Once daily",
                "items-0-notes": "",
            },
        )
        self.assertRedirects(
            response,
            reverse("prescriptions:detail", args=[self.prescription.pk]),
            fetch_redirect_response=False,
        )
        self.prescription.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.prescription.reference_number, "RX-UI-UPDATED")
        self.assertEqual(self.item.quantity_prescribed, Decimal("3.000"))

    def test_unauthorized_user_cannot_retrieve_or_update(self):
        self.client.force_login(self.denied)
        self.assertEqual(self.client.get(reverse("prescriptions:list")).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("prescriptions:update", args=[self.prescription.pk]), {}).status_code,
            403,
        )
