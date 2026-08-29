import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.catalog.models import Category, Manufacturer, Medicine
from apps.parties.models import Customer, Prescriber

from .forms import PrescriptionForm, PrescriptionItemForm, PrescriptionItemFormSet
from .models import Prescription, PrescriptionItem
from .queries import (
    get_prescription_for_detail,
    medicine_prescription_warning,
    prescription_list_queryset,
)
from .services import process_prescription_forms



class PrescriptionStringTests(SimpleTestCase):
    def test_reference_number_is_used_for_display(self):
        self.assertEqual(
            str(Prescription(reference_number="RX-100")),
            "RX-100",
        )


class PrescriptionWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.authorized_user = user_model.objects.create_user(
            username="prescription-owner"
        )
        cls.unauthorized_user = user_model.objects.create_user(
            username="prescription-accountant"
        )
        cls.editor_user = user_model.objects.create_user(
            username="prescription-editor"
        )
        cls.authorized_user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="prescriptions",
                codename__in={
                    "add_prescription",
                    "change_prescription",
                    "view_prescription",
                    "add_prescriptionitem",
                    "change_prescriptionitem",
                    "view_prescriptionitem",
                },
            )
        )
        cls.editor_user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="prescriptions",
                codename__in={
                    "change_prescription",
                    "view_prescription",
                    "change_prescriptionitem",
                    "view_prescriptionitem",
                },
            )
        )

        cls.category = Category.objects.create(name="Antibiotics")
        cls.manufacturer = Manufacturer.objects.create(name="Example Labs")
        cls.medicine = Medicine.objects.create(
            name="Prescription Medicine",
            category=cls.category,
            manufacturer=cls.manufacturer,
            prescription_required=True,
        )
        cls.other_medicine = Medicine.objects.create(
            name="Non-prescription Medicine",
            category=cls.category,
            manufacturer=cls.manufacturer,
            prescription_required=False,
        )
        cls.customer = Customer.objects.create(code="CUS-RX", name="Patient")
        cls.prescriber = Prescriber.objects.create(name="Dr Example")

    def prescription_data(self, **overrides):
        data = {
            "reference_number": "RX-200",
            "customer": "",
            "prescriber": "",
            "prescription_date": "2026-08-30",
            "notes": "",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-medicine": str(self.medicine.pk),
            "items-0-quantity_prescribed": "",
            "items-0-dosage_instructions": "",
            "items-0-notes": "",
        }
        data.update(overrides)
        return data

    def create_prescription(self, **overrides):
        values = {
            "reference_number": "RX-EXISTING",
            "prescription_date": date(2026, 8, 29),
            "created_by": self.authorized_user,
        }
        values.update(overrides)
        prescription = Prescription.objects.create(**values)
        item = PrescriptionItem.objects.create(
            prescription=prescription,
            medicine=self.medicine,
            quantity_prescribed=Decimal("1.000"),
            dosage_instructions="Existing instructions",
        )
        return prescription, item

    def test_forms_expose_only_approved_non_attachment_fields(self):
        self.assertEqual(
            tuple(PrescriptionForm().fields),
            (
                "reference_number",
                "customer",
                "prescriber",
                "prescription_date",
                "notes",
            ),
        )
        self.assertEqual(
            tuple(PrescriptionItemForm().fields),
            (
                "medicine",
                "quantity_prescribed",
                "dosage_instructions",
                "notes",
            ),
        )
        self.assertNotIn("attachment", PrescriptionForm().fields)

    def test_optional_quantity_instructions_and_notes_remain_optional(self):
        form = PrescriptionItemForm(
            data={
                "medicine": str(self.medicine.pk),
                "quantity_prescribed": "",
                "dosage_instructions": "",
                "notes": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["quantity_prescribed"])

    def test_nonpositive_prescribed_quantity_is_rejected(self):
        for quantity in ("0.000", "-0.001"):
            with self.subTest(quantity=quantity):
                form = PrescriptionItemForm(
                    data={
                        "medicine": str(self.medicine.pk),
                        "quantity_prescribed": quantity,
                        "dosage_instructions": "",
                        "notes": "",
                    }
                )

                self.assertFalse(form.is_valid())
                self.assertIn("quantity_prescribed", form.errors)

    def test_item_formset_requires_at_least_one_medicine(self):
        formset = PrescriptionItemFormSet(
            data=self.prescription_data(**{"items-0-medicine": ""}),
            instance=Prescription(),
        )

        self.assertFalse(formset.is_valid())
        self.assertTrue(formset.non_form_errors())

    def test_authorized_create_supports_optional_customer_and_prescriber(self):
        form, item_formset, prescription = process_prescription_forms(
            actor=self.authorized_user,
            data=self.prescription_data(),
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(item_formset.is_valid(), item_formset.errors)
        self.assertIsNotNone(prescription)
        self.assertEqual(prescription.created_by, self.authorized_user)
        self.assertIsNone(prescription.customer)
        self.assertIsNone(prescription.prescriber)
        self.assertFalse(bool(prescription.attachment))
        self.assertEqual(prescription.items.count(), 1)
        self.assertIsNone(prescription.items.get().quantity_prescribed)

    def test_authorized_create_preserves_metadata_and_item_details(self):
        form, item_formset, prescription = process_prescription_forms(
            actor=self.authorized_user,
            data=self.prescription_data(
                customer=str(self.customer.pk),
                prescriber=str(self.prescriber.pk),
                notes="Prescription note",
                **{
                    "items-0-quantity_prescribed": "2.500",
                    "items-0-dosage_instructions": "Use as directed",
                    "items-0-notes": "Item note",
                },
            ),
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(item_formset.is_valid(), item_formset.errors)
        self.assertEqual(prescription.customer, self.customer)
        self.assertEqual(prescription.prescriber, self.prescriber)
        self.assertEqual(prescription.notes, "Prescription note")
        item = prescription.items.get()
        self.assertEqual(item.quantity_prescribed, Decimal("2.500"))
        self.assertEqual(item.dosage_instructions, "Use as directed")
        self.assertEqual(item.notes, "Item note")

    def test_invalid_item_data_creates_nothing(self):
        form, item_formset, prescription = process_prescription_forms(
            actor=self.authorized_user,
            data=self.prescription_data(
                **{"items-0-quantity_prescribed": "0.000"}
            ),
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(item_formset.is_valid())
        self.assertIsNone(prescription)
        self.assertFalse(Prescription.objects.exists())

    def test_unauthorized_and_anonymous_callers_are_denied(self):
        for actor in (self.unauthorized_user, AnonymousUser()):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    process_prescription_forms(
                        actor=actor,
                        data=self.prescription_data(),
                    )

        self.assertFalse(Prescription.objects.exists())

    def test_authorized_update_preserves_creator_and_updates_existing_item(self):
        prescription, item = self.create_prescription()
        data = self.prescription_data(
            reference_number="RX-UPDATED",
            **{
                "items-INITIAL_FORMS": "1",
                "items-0-id": str(item.pk),
                "items-0-prescription": str(prescription.pk),
                "items-0-quantity_prescribed": "3.000",
                "items-0-dosage_instructions": "Updated instructions",
            },
        )

        form, item_formset, updated = process_prescription_forms(
            actor=self.editor_user,
            instance=prescription,
            data=data,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(item_formset.is_valid(), item_formset.errors)
        self.assertEqual(updated.created_by, self.authorized_user)
        self.assertEqual(updated.reference_number, "RX-UPDATED")
        item.refresh_from_db()
        self.assertEqual(item.quantity_prescribed, Decimal("3.000"))
        self.assertEqual(item.dosage_instructions, "Updated instructions")
        self.assertEqual(updated.items.count(), 1)

    def test_warning_query_exposes_only_nonclinical_flag_data(self):
        with self.assertNumQueries(1):
            warning = medicine_prescription_warning(self.medicine.pk)

        self.assertEqual(
            warning,
            {
                "medicine_id": self.medicine.pk,
                "prescription_required": True,
            },
        )

    def test_list_and_detail_queries_return_related_items_without_n_plus_one(self):
        older, _ = self.create_prescription(reference_number="RX-OLDER")
        newer, _ = self.create_prescription(
            reference_number="RX-NEWER",
            prescription_date=date(2026, 8, 30),
            customer=self.customer,
            prescriber=self.prescriber,
        )

        with self.assertNumQueries(2):
            prescriptions = list(prescription_list_queryset())
            self.assertEqual(prescriptions[0], newer)
            self.assertEqual(prescriptions[0].customer, self.customer)
            self.assertEqual(prescriptions[0].prescriber, self.prescriber)
            self.assertEqual(prescriptions[0].items.all()[0].medicine, self.medicine)

        with self.assertNumQueries(2):
            detail = get_prescription_for_detail(older.pk)
            self.assertEqual(detail.items.all()[0].medicine, self.medicine)

    def test_url_names_are_stable_and_namespaced(self):
        self.assertEqual(reverse("prescriptions:list"), "/prescriptions/")
        self.assertEqual(reverse("prescriptions:create"), "/prescriptions/new/")
        prescription_id = uuid.uuid4()
        self.assertEqual(
            reverse("prescriptions:detail", args=[prescription_id]),
            f"/prescriptions/{prescription_id}/",
        )

    def test_anonymous_and_unauthorized_users_cannot_retrieve_prescriptions(self):
        list_url = reverse("prescriptions:list")
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.unauthorized_user)
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse("prescriptions:create"),
            data=self.prescription_data(),
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Prescription.objects.exists())

    @patch("apps.prescriptions.views.render", return_value=HttpResponse("ok"))
    def test_authorized_list_and_detail_handlers_expose_stable_context(self, mocked_render):
        prescription, _ = self.create_prescription()
        self.client.force_login(self.authorized_user)

        list_response = self.client.get(reverse("prescriptions:list"))
        self.assertEqual(list_response.status_code, 200)
        list_context = mocked_render.call_args.args[2]
        self.assertEqual(list_context["page_context"], "Prescriptions")
        self.assertEqual(list(list_context["prescriptions"]), [prescription])

        detail_response = self.client.get(
            reverse("prescriptions:detail", args=[prescription.pk])
        )
        self.assertEqual(detail_response.status_code, 200)
        detail_context = mocked_render.call_args.args[2]
        self.assertEqual(detail_context["prescription"], prescription)

    @patch("apps.prescriptions.views.render", return_value=HttpResponse("ok"))
    def test_create_get_exposes_backend_form_contract_without_attachment(self, mocked_render):
        self.client.force_login(self.authorized_user)

        response = self.client.get(reverse("prescriptions:create"))

        self.assertEqual(response.status_code, 200)
        context = mocked_render.call_args.args[2]
        self.assertEqual(context["page_context"], "New prescription")
        self.assertFalse(context["attachment_upload_enabled"])
        self.assertNotIn("attachment", context["form"].fields)
        self.assertEqual(context["item_formset"].prefix, "items")

    def test_authorized_create_handler_persists_and_redirects(self):
        self.client.force_login(self.authorized_user)

        response = self.client.post(
            reverse("prescriptions:create"),
            data=self.prescription_data(),
        )

        prescription = Prescription.objects.get()
        self.assertRedirects(
            response,
            reverse("prescriptions:detail", args=[prescription.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(prescription.created_by, self.authorized_user)

    @patch("apps.prescriptions.views.render", return_value=HttpResponse("invalid"))
    def test_attachment_upload_is_explicitly_disabled(self, mocked_render):
        self.client.force_login(self.authorized_user)
        data = self.prescription_data()
        data["attachment"] = SimpleUploadedFile(
            "prescription.txt",
            b"not stored",
            content_type="text/plain",
        )

        response = self.client.post(reverse("prescriptions:create"), data=data)

        self.assertEqual(response.status_code, 200)
        context = mocked_render.call_args.args[2]
        self.assertFalse(context["attachment_upload_enabled"])
        self.assertIn("not enabled", str(context["form"].non_field_errors()))
        self.assertFalse(Prescription.objects.exists())
