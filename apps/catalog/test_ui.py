import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import Category, Manufacturer, Medicine, MedicineBarcode, MedicineUnit


class CatalogWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="catalog-ui")
        cls.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="catalog"))
        cls.category = Category.objects.create(name="Analgesics")
        cls.manufacturer = Manufacturer.objects.create(name="Example manufacturer")
        cls.medicine = Medicine.objects.create(
            name="Example 500 mg", generic_name="Example generic", category=cls.category,
            manufacturer=cls.manufacturer, default_selling_price="0.1250",
        )
        cls.unit = MedicineUnit.objects.create(
            medicine=cls.medicine, name="Tablet", conversion_to_base=1, is_base_unit=True,
        )
        MedicineBarcode.objects.create(medicine_unit=cls.unit, barcode="001234567890")

    def setUp(self):
        self.client.force_login(self.user)

    def test_search_follows_units_to_barcodes_and_combines_status(self):
        url = reverse("catalog:medicine-list")
        for query in ("Example 500", "Example generic", "001234567890"):
            with self.subTest(query=query):
                response = self.client.get(url, {"q": query, "status": "all"})
                self.assertEqual(list(response.context["medicines"]), [self.medicine])
                self.assertContains(response, 'value="all" selected')
        self.medicine.is_active = False
        self.medicine.save()
        self.assertFalse(self.client.get(url, {"q": "Example"}).context["medicines"])
        response = self.client.get(url, {"q": "Example", "status": "inactive"})
        self.assertEqual(list(response.context["medicines"]), [self.medicine])

    def test_create_renders_required_base_unit_and_retains_invalid_values(self):
        url = reverse("catalog:medicine-create")
        self.assertContains(self.client.get(url), 'name="base_unit_name"')
        response = self.client.post(url, {
            "name": "Keep this name", "category": self.category.pk,
            "manufacturer": self.manufacturer.pk, "default_selling_price": "-1",
            "base_unit_name": "Tablet", "prescription_required": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Keep this name"')
        self.assertContains(response, 'id="id_default_selling_price-error"')
        self.assertContains(response, 'value="Tablet"')
        self.assertEqual(Medicine.objects.count(), 1)

    def test_edit_unit_preserves_unchecked_values_after_validation(self):
        url = reverse("catalog:medicine-unit-update", args=[self.medicine.pk, self.unit.pk])
        response = self.client.post(url, {"name": "Tablet", "conversion_to_base": "2", "is_base_unit": "on"})
        for name in ("purchase_allowed", "sale_allowed"):
            tag = re.search(r'<input\s[^>]*name="' + name + r'"[^>]*>', response.content.decode()).group()
            self.assertNotIn("checked", tag)
        self.assertContains(response, "A base unit must have a conversion factor of 1.")

    def test_catalog_pages_render_with_explicit_breadcrumbs(self):
        routes = [
            ("medicine-list", []), ("medicine-create", []),
            ("medicine-detail", [self.medicine.pk]), ("medicine-update", [self.medicine.pk]),
            ("medicine-unit-create", [self.medicine.pk]),
            ("medicine-unit-update", [self.medicine.pk, self.unit.pk]),
            ("medicine-barcode-create", [self.medicine.pk]),
            ("category-list", []), ("category-create", []), ("category-update", [self.category.pk]),
            ("manufacturer-list", []), ("manufacturer-create", []),
            ("manufacturer-update", [self.manufacturer.pk]),
        ]
        for route, args in routes:
            with self.subTest(route=route):
                response = self.client.get(reverse(f"catalog:{route}", args=args))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(re.findall(r"<h1\b", response.content.decode())), 1)
                breadcrumbs = response.context["breadcrumbs"]
                self.assertEqual(breadcrumbs[0]["label"], "Catalog")
                self.assertNotIn("url", breadcrumbs[-1])
                self.assertNotEqual(breadcrumbs[-1]["label"], route)
                navigation = response.content.decode().split(
                    'aria-label="Catalog sections"', 1,
                )[1].split("</nav>", 1)[0]
                active_links = re.findall(r'<a href="([^"]+)" aria-current="page"', navigation)
                section = route.split("-", 1)[0]
                self.assertEqual(active_links, [reverse(f"catalog:{section}-list")])
                for label in ("Medicines", "Categories", "Manufacturers"):
                    self.assertIn(f">{label}</a>", navigation)

    def test_view_only_users_cannot_see_write_actions(self):
        self.user.user_permissions.set(Permission.objects.filter(
            content_type__app_label="catalog", codename="view_medicine",
        ))
        response = self.client.get(reverse("catalog:medicine-detail", args=[self.medicine.pk]))
        for text in ("Edit medicine", "Add unit", "Add barcode", "Deactivate"):
            self.assertNotContains(response, text)
        self.assertNotContains(self.client.get(reverse("catalog:medicine-list")), "Add medicine")

        for section, permission in (
            ("medicine", "view_medicine"),
            ("category", "view_category"),
            ("manufacturer", "view_manufacturer"),
        ):
            with self.subTest(section=section):
                self.user.user_permissions.set(Permission.objects.filter(
                    content_type__app_label="catalog", codename=permission,
                ))
                response = self.client.get(reverse(f"catalog:{section}-list"))
                navigation = response.content.decode().split(
                    'aria-label="Catalog sections"', 1,
                )[1].split("</nav>", 1)[0]
                self.assertEqual(
                    re.findall(r'<a href="([^"]+)"', navigation),
                    [reverse(f"catalog:{section}-list")],
                )

    def test_unit_barcode_and_reference_post_flows(self):
        response = self.client.post(reverse("catalog:medicine-unit-create", args=[self.medicine.pk]), {
            "name": "Box", "conversion_to_base": "10", "purchase_allowed": "on",
        })
        self.assertEqual(response.status_code, 302)
        unit = self.medicine.units.get(name="Box")
        self.assertFalse(unit.sale_allowed)
        response = self.client.post(reverse("catalog:medicine-barcode-create", args=[self.medicine.pk]), {
            "medicine_unit": unit.pk, "barcode": "00990099",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(unit.barcodes.filter(barcode="00990099").exists())
        for route, model in (("category", Category), ("manufacturer", Manufacturer)):
            response = self.client.post(reverse(f"catalog:{route}-create"), {"name": "New reference"})
            self.assertEqual(response.status_code, 302)
            record = model.objects.get(name="New reference")
            self.assertEqual(self.client.post(reverse(f"catalog:{route}-update", args=[record.pk]), {"name": "Updated reference"}).status_code, 302)
            record.refresh_from_db()
            self.assertEqual(record.name, "Updated reference")

    def test_create_only_breadcrumb_does_not_link_to_forbidden_registry(self):
        self.user.user_permissions.set(Permission.objects.filter(
            content_type__app_label="catalog", codename="add_medicine",
        ))
        response = self.client.get(reverse("catalog:medicine-create"))
        self.assertTrue(all("url" not in item for item in response.context["breadcrumbs"]))
        self.assertNotContains(response, 'aria-label="Catalog sections"')

    def test_medicine_edit_keeps_the_existing_base_unit(self):
        url = reverse("catalog:medicine-update", args=[self.medicine.pk])
        self.assertNotContains(self.client.get(url), 'name="base_unit_name"')
        response = self.client.post(url, {
            "name": "Updated medicine", "category": self.category.pk,
            "manufacturer": self.manufacturer.pk, "default_selling_price": "0.3750",
            "low_stock_threshold_base": "12.500", "prescription_required": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.medicine.refresh_from_db()
        self.assertEqual(self.medicine.name, "Updated medicine")
        self.assertTrue(self.medicine.prescription_required)
        self.assertEqual(self.medicine.units.get(is_base_unit=True).pk, self.unit.pk)
