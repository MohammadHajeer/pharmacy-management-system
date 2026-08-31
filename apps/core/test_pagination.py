from html import unescape
import re
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from .pagination import DEFAULT_PAGE_SIZE, pagination_context


class PaginationComponentTests(SimpleTestCase):
    def render_pagination(self, total, query=""):
        request = RequestFactory().get("/registry/" + query)
        request.user = AnonymousUser()
        context = pagination_context(request, range(total), context_name="rows")
        return render_to_string(
            "components/pagination.html", {**context, "label": "medicines"}, request=request,
        )

    def test_standard_page_size(self):
        self.assertEqual(DEFAULT_PAGE_SIZE, 25)

    def test_links_replace_only_page_and_escape_encoded_repeated_parameters(self):
        query = "?q=A%26B+%22test%22&status=all&sort=name&tag=a&tag=b&page=3&page=2"
        html = self.render_pagination(100, query)
        expected = parse_qs(urlsplit(query).query)
        links = re.findall(r'href="([^"]+)"', html)
        self.assertTrue(links)
        for href in links:
            params = parse_qs(urlsplit(unescape(href)).query)
            self.assertEqual(len(params.pop("page")), 1)
            self.assertEqual(params, {k: v for k, v in expected.items() if k != "page"})
        self.assertIn("&amp;", html)

    def test_large_page_range_is_elided_and_current_page_is_accessible(self):
        html = self.render_pagination(500, "?page=10")
        self.assertIn("Showing 226–250 of 500 medicines", html)
        self.assertIn('aria-label="Pagination"', html)
        self.assertIn('aria-current="page" aria-label="Current page, page 10"', html)
        self.assertIn("Page 10 of 20", html)
        self.assertIn("…", html)
        self.assertNotIn('aria-label="Page 4"', html)
        self.assertLess(len(re.findall(r"href=", html)), 10)

    def test_first_and_last_page_use_non_link_disabled_controls(self):
        for query, label in (("", "Previous page"), ("?page=2", "Next page")):
            with self.subTest(label=label):
                html = self.render_pagination(30, query)
                self.assertRegex(html, '<span[^>]+aria-disabled="true" aria-label="' + label + '"')
                self.assertNotRegex(html, '<a[^>]+aria-label="' + label + '"')

    def test_single_page_has_count_without_navigation_and_empty_has_no_footer(self):
        html = self.render_pagination(8)
        self.assertIn("Showing 1–8 of 8 medicines", html)
        self.assertNotIn("<nav", html)
        self.assertEqual(self.render_pagination(0, "?page=999").strip(), "")
