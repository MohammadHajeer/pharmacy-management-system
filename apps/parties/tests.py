from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Customer, Supplier


class PartyStringTests(SimpleTestCase):
    def test_supplier_string_includes_code_and_name(self):
        self.assertEqual(str(Supplier(code="SUP-1", name="Acme")), "SUP-1 — Acme")

    def test_customer_string_includes_code_and_name(self):
        self.assertEqual(str(Customer(code="CUS-1", name="Sam")), "CUS-1 — Sam")


class SupplierWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="supplier-workflow-user")
        cls.view_permission = Permission.objects.get(
            content_type__app_label="parties",
            codename="view_supplier",
        )
        cls.add_permission = Permission.objects.get(
            content_type__app_label="parties",
            codename="add_supplier",
        )
        cls.change_permission = Permission.objects.get(
            content_type__app_label="parties",
            codename="change_supplier",
        )
        cls.supplier = Supplier.objects.create(
            code="SUP-WORKFLOW",
            name="Workflow Medical Supply",
        )

    def test_supplier_list_requires_permission(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("parties:supplier-list"))

        self.assertEqual(response.status_code, 403)

    def test_authorized_supplier_search_uses_existing_records(self):
        self.user.user_permissions.add(self.view_permission)
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("parties:supplier-list"),
            {"q": "Workflow Medical"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["suppliers"]), [self.supplier])

    def test_supplier_code_is_case_insensitively_unique_in_the_form_workflow(self):
        self.user.user_permissions.add(self.add_permission)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("parties:supplier-create"),
            {
                "code": "sup-workflow",
                "name": "Duplicate supplier",
                "contact_person": "",
                "phone": "",
                "email": "",
                "address": "",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A supplier with this code already exists.")
        self.assertEqual(Supplier.objects.count(), 1)

    def test_supplier_is_deactivated_instead_of_deleted(self):
        self.user.user_permissions.add(self.change_permission)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("parties:supplier-toggle-active", args=[self.supplier.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.supplier.refresh_from_db()
        self.assertFalse(self.supplier.is_active)
        self.assertTrue(Supplier.objects.filter(pk=self.supplier.pk).exists())
