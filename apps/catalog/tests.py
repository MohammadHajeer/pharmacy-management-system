from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import MedicineUnit
from .unit_economics import (
    acquisition_cost_per_base_unit,
    base_quantity,
    selected_unit_selling_price,
)


class MedicineListViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="catalog-user")
        self.url = reverse("catalog:medicine-list")

    def test_medicine_list_requires_its_existing_permission(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_medicine_list_uses_explicit_catalog_breadcrumbs(self):
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="catalog",
                codename="view_medicine",
            )
        )
        self.client.force_login(self.user)

        response = self.client.get(self.url)
        breadcrumb_html = response.content.decode().split(
            'aria-label="Breadcrumb"',
            1,
        )[1].split("</nav>", 1)[0]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["breadcrumbs"],
            [{"label": "Catalog"}, {"label": "Medicines"}],
        )
        self.assertIn("Catalog", breadcrumb_html)
        self.assertIn('aria-current="page" title="Medicines"', breadcrumb_html)
        self.assertNotIn("medicine-list", breadcrumb_html.lower())
        self.assertNotIn('href="/catalog/medicines/"', breadcrumb_html)


class MedicineUnitValidationTests(SimpleTestCase):
    def test_base_unit_requires_conversion_of_one(self):
        unit = MedicineUnit(is_base_unit=True, conversion_to_base=Decimal("2"))

        with self.assertRaises(ValidationError):
            unit.clean()


class UnitEconomicsTests(SimpleTestCase):
    def test_selected_units_convert_to_base_quantity(self):
        self.assertEqual(
            base_quantity(Decimal("2.000"), Decimal("20.000000")),
            Decimal("40.000"),
        )

    def test_base_unit_selling_price_converts_to_selected_unit_price(self):
        self.assertEqual(
            selected_unit_selling_price(
                Decimal("0.2500"),
                Decimal("20.000000"),
            ),
            Decimal("5.0000"),
        )

    def test_selected_purchase_unit_cost_converts_to_base_unit_cost(self):
        self.assertEqual(
            acquisition_cost_per_base_unit(
                Decimal("8.0000"),
                Decimal("20.000000"),
            ),
            Decimal("0.4000"),
        )

    def test_base_quantity_uses_three_decimal_half_up_rounding(self):
        self.assertEqual(
            base_quantity(Decimal("0.001"), Decimal("0.500000")),
            Decimal("0.001"),
        )
