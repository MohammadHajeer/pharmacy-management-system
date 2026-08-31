from uuid import UUID

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from apps.core.pagination import DEFAULT_PAGE_SIZE

from .models import Customer, Prescriber, Supplier


class PartyPaginationTests(TestCase):
    registries = (("customer", Customer), ("supplier", Supplier), ("prescriber", Prescriber))

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="party-pagination")
        cls.user.user_permissions.set(Permission.objects.filter(
            content_type__app_label="parties", codename__startswith="view_",
        ))
        for route, model in cls.registries:
            model.objects.bulk_create([
                model(
                    id=UUID(int=i), name="Matched party" if i <= 28 else "Other party",
                    **({"code": f"PAGE-{i}"} if route != "prescriber" else {}),
                )
                for i in range(31, 0, -1)
            ])
            model.objects.create(
                name="Inactive party", is_active=False,
                **({"code": "INACTIVE"} if route != "prescriber" else {}),
            )

    def setUp(self):
        self.client.force_login(self.user)

    def test_all_registries_use_sliced_stable_pages_and_filtered_counts(self):
        for route, model in self.registries:
            with self.subTest(registry=route):
                url = reverse(f"parties:{route}-list")
                first = self.client.get(url)
                second = self.client.get(url, {"page": 2})
                self.assertEqual(len(first.context[route + "s"]), DEFAULT_PAGE_SIZE)
                self.assertEqual(len(second.context[route + "s"]), 6)
                self.assertEqual(second.context[route + "s"].query.low_mark, DEFAULT_PAGE_SIZE)
                seen = list(first.context[route + "s"]) + list(second.context[route + "s"])
                self.assertEqual([row.pk for row in seen], [UUID(int=i) for i in range(1, 32)])
                filtered = self.client.get(url, {"q": "Matched", "status": "active", "page": 2})
                self.assertEqual(len(filtered.context[route + "s"]), 3)
                self.assertContains(filtered, f"Showing 26–28 of 28 {route}s")
                self.assertContains(filtered, '?q=Matched&amp;status=active&amp;page=1')

    def test_empty_single_page_and_invalid_page_values(self):
        for route, model in self.registries:
            url = reverse(f"parties:{route}-list")
            with self.subTest(registry=route):
                for value, expected in (("abc", 1), ("-10", 2), ("99999", 2)):
                    self.assertEqual(self.client.get(url, {"page": value}).context["page_obj"].number, expected)
                empty = self.client.get(url, {"q": "no-match", "page": 99})
                self.assertContains(empty, f"No {route}s found")
                self.assertContains(empty, "Clear filters")
                self.assertNotContains(empty, 'aria-label="Pagination"')
                single = self.client.get(url, {"status": "inactive", "page": 99})
                self.assertContains(single, f"Showing 1–1 of 1 {route}s")
                self.assertNotContains(single, 'aria-label="Pagination"')
                self.assertNotContains(single, 'name="page"')

    def test_all_registry_permissions_still_apply_on_later_pages(self):
        self.client.logout()
        for route, model in self.registries:
            self.assertEqual(self.client.get(reverse(f"parties:{route}-list"), {"page": 2}).status_code, 302)
        self.user.user_permissions.clear()
        self.client.force_login(self.user)
        for route, model in self.registries:
            self.assertEqual(self.client.get(reverse(f"parties:{route}-list"), {"page": 2}).status_code, 403)
