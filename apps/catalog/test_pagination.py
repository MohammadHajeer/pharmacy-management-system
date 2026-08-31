from html import unescape
import re
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.core.pagination import DEFAULT_PAGE_SIZE, pagination_context

from .models import Category, Manufacturer, Medicine, MedicineBarcode, MedicineUnit


class MedicinePaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="medicine-pagination")
        cls.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="catalog", codename="view_medicine",
        ))
        cls.category = Category.objects.create(name="Pagination category")
        cls.manufacturer = Manufacturer.objects.create(name="Pagination manufacturer")
        # Duplicate names and deliberately reversed IDs exercise the tie-breaker.
        Medicine.objects.bulk_create([
            Medicine(
                id=UUID(int=i), name="Matched medicine" if i <= 30 else "Other medicine",
                category=cls.category, manufacturer=cls.manufacturer,
            )
            for i in range(53, 0, -1)
        ])
        Medicine.objects.create(
            name="Matched inactive", is_active=False,
            category=cls.category, manufacturer=cls.manufacturer,
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("catalog:medicine-list")

    def test_pages_are_sliced_in_sql_with_stable_non_overlapping_order(self):
        seen = []
        for number, count in ((1, DEFAULT_PAGE_SIZE), (2, DEFAULT_PAGE_SIZE), (3, 3)):
            response = self.client.get(self.url, {"page": number})
            rows = response.context["medicines"]
            self.assertEqual(len(rows), count)
            self.assertEqual(rows.query.order_by, ("name", "id"))
            self.assertEqual(rows.query.low_mark, (number - 1) * DEFAULT_PAGE_SIZE)
            self.assertEqual(rows.query.high_mark, min(number * DEFAULT_PAGE_SIZE, 53))
            seen.extend(row.pk for row in rows)
        self.assertEqual(seen, [UUID(int=i) for i in range(1, 54)])

    def test_filtered_count_and_links_keep_search_status_and_other_parameters(self):
        response = self.client.get(self.url, {
            "q": "Matched medicine", "status": "active", "sort": "name", "page": 2,
        })
        self.assertEqual(len(response.context["medicines"]), 5)
        self.assertContains(response, "Showing 26–30 of 30 medicines")
        nav = re.search(r'<nav aria-label="Pagination".*?</nav>', response.content.decode(), re.S).group()
        for href in re.findall(r'href="([^"]+)"', nav):
            params = parse_qs(urlsplit(unescape(href)).query)
            self.assertEqual(params, {
                "q": ["Matched medicine"], "status": ["active"], "sort": ["name"], "page": ["1"],
            })

    def test_search_joins_do_not_duplicate_paginated_medicines(self):
        unit = MedicineUnit.objects.create(
            medicine_id=UUID(int=1), name="Tablet", conversion_to_base=1, is_base_unit=True,
        )
        MedicineBarcode.objects.bulk_create([
            MedicineBarcode(medicine_unit=unit, barcode=f"PAGINATION-{i}") for i in range(2)
        ])
        response = self.client.get(self.url, {"q": "Matched medicine"})
        self.assertEqual(response.context["page_obj"].paginator.count, 30)
        self.assertEqual(len({row.pk for row in response.context["medicines"]}), DEFAULT_PAGE_SIZE)

    def test_invalid_and_out_of_range_pages_are_graceful(self):
        for value, expected in (("abc", 1), ("-10", 3), ("0", 3), ("99999", 3)):
            with self.subTest(page=value):
                response = self.client.get(self.url, {"page": value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["page_obj"].number, expected)

    def test_empty_and_single_page_results_keep_empty_state_without_controls(self):
        response = self.client.get(self.url, {"q": "no-match", "page": 99})
        self.assertContains(response, "No medicines found")
        self.assertContains(response, "Clear filters")
        self.assertNotContains(response, 'aria-label="Pagination"')
        self.assertNotContains(response, "Showing ")
        self.assertEqual(response.context["page_obj"].paginator.count, 0)
        response = self.client.get(self.url, {"status": "inactive", "page": 99})
        self.assertContains(response, "Showing 1–1 of 1 medicines")
        self.assertNotContains(response, 'aria-label="Pagination"')

    def test_filter_form_and_clear_action_do_not_carry_page_state(self):
        response = self.client.get(self.url, {"q": "Matched", "status": "all", "page": 2})
        form = re.search(r'<form[^>]+data-registry-filter-form.*?</form>', response.content.decode(), re.S).group()
        self.assertIn(f'action="{self.url}"', form)
        self.assertNotIn('name="page"', form)
        self.assertIn(f'href="{self.url}"', form)
        self.assertEqual(self.client.get(self.url, {"q": "Other"}).context["page_obj"].number, 1)

    def test_related_objects_are_loaded_only_for_the_current_page_without_n_plus_one(self):
        request = RequestFactory().get(self.url, {"page": 2})
        queryset = Medicine.objects.select_related("category", "manufacturer").order_by("name", "id")
        with self.assertNumQueries(1):
            context = pagination_context(request, queryset, context_name="medicines")
        self.assertIsNone(queryset._result_cache)
        with self.assertNumQueries(1):
            rows = list(context["medicines"])
        self.assertEqual(len(rows), DEFAULT_PAGE_SIZE)
        with self.assertNumQueries(0):
            for row in rows:
                self.assertEqual(row.category.name, self.category.name)
                self.assertEqual(row.manufacturer.name, self.manufacturer.name)

    def test_pagination_does_not_bypass_permissions(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url, {"page": 2}).status_code, 302)
        self.user.user_permissions.clear()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url, {"page": 2}).status_code, 403)
