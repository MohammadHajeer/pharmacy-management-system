from django.test import SimpleTestCase

from .models import Customer, Supplier


class PartyStringTests(SimpleTestCase):
    def test_supplier_string_includes_code_and_name(self):
        self.assertEqual(str(Supplier(code="SUP-1", name="Acme")), "SUP-1 — Acme")

    def test_customer_string_includes_code_and_name(self):
        self.assertEqual(str(Customer(code="CUS-1", name="Sam")), "CUS-1 — Sam")
