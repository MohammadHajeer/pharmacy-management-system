from uuid import UUID

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.pagination import DEFAULT_PAGE_SIZE, pagination_context
from apps.parties.models import Supplier

from .models import PurchaseInvoice


class PurchasePaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="purchase-pagination")
        cls.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="purchasing", codename="view_purchaseinvoice",
        ))
        cls.supplier = Supplier.objects.create(code="PAGINATION", name="Pagination supplier")
        PurchaseInvoice.objects.bulk_create([
            PurchaseInvoice(
                id=UUID(int=i), supplier=cls.supplier, created_by=cls.user,
                invoice_date=timezone.localdate(), currency_code="USD",
            )
            for i in range(1, 31)
        ])
        # Matching timestamps force the descending UUID tie-breaker at a page boundary.
        PurchaseInvoice.objects.update(created_at=timezone.now())

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("purchasing:purchase-invoice-list")

    def test_pages_keep_newest_first_order_with_unique_tie_breaker(self):
        first = self.client.get(self.url)
        second = self.client.get(self.url, {"page": 2, "supplier": self.supplier.pk, "sort": "date"})
        self.assertEqual(len(first.context["invoices"]), DEFAULT_PAGE_SIZE)
        self.assertEqual(len(second.context["invoices"]), 5)
        self.assertEqual(second.context["invoices"].query.low_mark, DEFAULT_PAGE_SIZE)
        self.assertEqual(second.context["invoices"].query.order_by, ("-created_at", "-id"))
        seen = list(first.context["invoices"]) + list(second.context["invoices"])
        self.assertEqual([row.pk for row in seen], [UUID(int=i) for i in range(30, 0, -1)])
        self.assertContains(second, "Showing 26–30 of 30 purchase invoices")
        self.assertContains(second, f'?page=1&amp;supplier={self.supplier.pk}&amp;sort=date')

    def test_invalid_pages_empty_and_one_page_results(self):
        for value, expected in (("abc", 1), ("-10", 2), ("99999", 2)):
            self.assertEqual(self.client.get(self.url, {"page": value}).context["page_obj"].number, expected)
        PurchaseInvoice.objects.exclude(pk=UUID(int=1)).delete()
        single = self.client.get(self.url, {"page": 2})
        self.assertContains(single, "Showing 1–1 of 1 purchase invoices")
        self.assertNotContains(single, 'aria-label="Pagination"')
        PurchaseInvoice.objects.all().delete()
        empty = self.client.get(self.url, {"page": 999})
        self.assertContains(empty, "No purchase invoices yet")
        self.assertNotContains(empty, 'aria-label="Pagination"')

    def test_supplier_join_is_preserved_without_per_row_queries(self):
        with self.assertNumQueries(1):
            context = pagination_context(
                RequestFactory().get(self.url),
                PurchaseInvoice.objects.select_related("supplier").order_by("-created_at", "-id"),
                context_name="invoices",
            )
        with self.assertNumQueries(1):
            rows = list(context["invoices"])
        with self.assertNumQueries(0):
            self.assertTrue(all(row.supplier.name == self.supplier.name for row in rows))

    def test_pagination_preserves_permission_checks(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url, {"page": 2}).status_code, 302)
        self.user.user_permissions.clear()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url, {"page": 2}).status_code, 403)
