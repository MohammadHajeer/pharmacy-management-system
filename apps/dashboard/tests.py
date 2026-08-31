from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import resolve, reverse

from config.context_processors import dashboard_navigation


class SharedComponentTests(SimpleTestCase):
    def test_registry_filters_have_get_fallback_and_only_show_useful_reset(self):
        for query_string, query, status, show_clear in (
            ("", "", "active", False),
            ("?q=Example", "Example", "active", True),
            ("?status=inactive", "", "inactive", True),
        ):
            request = RequestFactory().get("/catalog/medicines/" + query_string)
            request.user = AnonymousUser()
            request.resolver_match = resolve("/catalog/medicines/")
            rendered = render_to_string("components/registry_filters.html", {
                "clear_url": "/catalog/medicines/", "search_label": "Search medicines",
                "search_placeholder": "Name, generic name or barcode",
                "query": query, "status": status,
                "status_options": [{"value": "active", "label": "Active"}],
            }, request=request)
            with self.subTest(query_string=query_string):
                self.assertIn('method="get" action="/catalog/medicines/"', rendered)
                self.assertIn("data-registry-filter-form", rendered)
                self.assertIn('name="q"', rendered)
                self.assertIn("<noscript>", rendered)
                self.assertIn("Apply filters", rendered)
                self.assertEqual("Clear filters" in rendered, show_clear)
                enhanced = rendered.split("<noscript>")[0] + rendered.split("</noscript>")[1]
                self.assertNotIn('type="submit"', enhanced)

    def test_numeric_input_preserves_zero_minimum_and_decimal_step(self):
        rendered = render_to_string("components/input.html", {
            "name": "unit_cost", "type": "number", "step": "0.0001", "min": 0, "max": 100,
        })
        self.assertIn('min="0"', rendered)
        self.assertIn('max="100"', rendered)
        self.assertIn('step="0.0001"', rendered)
        ordinary = render_to_string("components/input.html", {"name": "name"})
        self.assertNotIn('min="', ordinary)
        self.assertNotIn('max="', ordinary)

    def test_topbar_renders_explicit_breadcrumbs_not_raw_route_names(self):
        request = RequestFactory().get("/catalog/medicines/")
        request.user = AnonymousUser()
        request.resolver_match = resolve("/catalog/medicines/")

        rendered = render_to_string(
            "components/topbar.html",
            {
                "breadcrumbs": [
                    {"label": "Medicines", "url": "/catalog/medicines/"},
                    {"label": "Panadol 500mg"},
                ]
            },
            request=request,
        )

        self.assertIn('aria-label="Breadcrumb"', rendered)
        self.assertIn('<a href="/catalog/medicines/"', rendered)
        self.assertIn('aria-current="page"', rendered)
        self.assertIn("Panadol 500mg", rendered)
        self.assertNotIn("Pharmacy operations", rendered)
        self.assertNotIn("medicine-list", rendered.lower())

    def test_icon_selects_named_path_and_applies_shared_svg_attributes(self):
        rendered = render_to_string(
            "components/icon.html",
            {"name": "dashboard", "class": "size-5 text-slate-500"},
        )

        self.assertIn('class="size-5 text-slate-500"', rendered)
        self.assertIn('viewBox="0 0 24 24"', rendered)
        self.assertIn('fill="none"', rendered)
        self.assertIn('stroke="currentColor"', rendered)
        self.assertIn('stroke-width="1.8"', rendered)
        self.assertIn('aria-hidden="true"', rendered)
        self.assertIn("M4 4h6v6H4z", rendered)
        self.assertNotIn("M4 7h16M4 12h16M4 17h16", rendered)

    def test_icon_renders_nothing_for_an_unknown_name(self):
        rendered = render_to_string(
            "components/icon.html",
            {"name": "not-registered", "class": "size-5"},
        )

        self.assertEqual(rendered.strip(), "")

    def test_button_supports_new_variants_and_sizes_with_legacy_danger_alias(self):
        destructive = render_to_string(
            "components/button.html",
            {"text": "Delete", "variant": "destructive", "size": "sm"},
        )
        legacy_danger = render_to_string(
            "components/button.html",
            {"text": "Delete", "variant": "danger"},
        )

        self.assertIn("h-8", destructive)
        self.assertIn("bg-red-600", destructive)
        self.assertIn("bg-red-600", legacy_danger)

    def test_input_associates_help_and_errors_and_supports_readonly(self):
        rendered = render_to_string(
            "components/input.html",
            {
                "id": "id_reference",
                "name": "reference",
                "label": "Reference",
                "help_text": "Generated by the system.",
                "error": "This value is invalid.",
                "readonly": True,
            },
        )

        self.assertIn('for="id_reference"', rendered)
        self.assertIn("readonly", rendered)
        self.assertIn('aria-invalid="true"', rendered)
        self.assertIn(
            'aria-describedby="id_reference-help id_reference-error"',
            rendered,
        )
        self.assertIn('id="id_reference-help"', rendered)
        self.assertIn('id="id_reference-error"', rendered)

    def test_checkbox_preserves_native_semantics_and_shared_visual_states(self):
        rendered = render_to_string(
            "components/checkbox.html",
            {
                "id": "id_is_active",
                "name": "is_active",
                "value": "yes",
                "checked": True,
                "required": True,
                "label": "Active",
                "description": "Available for new work.",
                "error": "Review this setting.",
                "aria_describedby": "options-help",
            },
        )

        self.assertIn('for="id_is_active"', rendered)
        self.assertIn('name="is_active"', rendered)
        self.assertIn('type="checkbox"', rendered)
        self.assertIn('value="yes"', rendered)
        self.assertIn("checked", rendered)
        self.assertIn("required", rendered)
        self.assertIn('aria-invalid="true"', rendered)
        self.assertIn(
            'aria-describedby="options-help id_is_active-help id_is_active-error"',
            rendered,
        )
        self.assertIn("appearance-none", rendered)
        self.assertIn("ring-red-500", rendered)
        self.assertIn("peer-checked:bg-primary-600", rendered)
        self.assertIn("peer-focus-visible:ring-primary-600", rendered)
        self.assertIn('id="id_is_active-help"', rendered)
        self.assertIn('id="id_is_active-error"', rendered)

    def test_checkbox_supports_disabled_checked_state(self):
        rendered = render_to_string(
            "components/checkbox.html",
            {
                "name": "is_active",
                "checked": True,
                "disabled": True,
                "label": "Active",
            },
        )

        self.assertIn("disabled", rendered)
        self.assertIn("cursor-not-allowed", rendered)
        self.assertIn("border-slate-300 bg-slate-300", rendered)
        self.assertIn("opacity-100", rendered)

    def test_textarea_and_select_share_accessible_supporting_text(self):
        textarea = render_to_string(
            "components/textarea.html",
            {
                "name": "notes",
                "help_text": "For internal use.",
                "readonly": True,
            },
        )
        select = render_to_string(
            "components/select.html",
            {
                "name": "category",
                "help_text": "Choose one category.",
                "options": [{"value": "otc", "label": "OTC"}],
            },
        )

        self.assertIn('aria-describedby="notes-help"', textarea)
        self.assertIn("readonly", textarea)
        self.assertIn('aria-describedby="category-help"', select)
        self.assertIn("appearance-none", select)
        self.assertIn('name="category"', select)
        self.assertIn("data-custom-select-native", select)
        self.assertIn("data-custom-select-trigger", select)
        self.assertIn('role="combobox"', select)
        self.assertIn('role="listbox"', select)

    def test_select_preserves_initial_required_and_disabled_option_state(self):
        rendered = render_to_string(
            "components/select.html",
            {
                "name": "tax_rate",
                "label": "Tax rate",
                "required": True,
                "value": "vat",
                "options": [
                    {"value": "zero", "label": "Zero", "disabled": True},
                    {"value": "vat", "label": "VAT"},
                ],
            },
        )

        self.assertIn('name="tax_rate"', rendered)
        self.assertIn("required", rendered)
        self.assertIn('value="vat" selected', rendered)
        self.assertIn('value="zero"  disabled', rendered)
        self.assertIn('data-value="vat" aria-selected="true"', rendered)
        self.assertIn('data-value="zero" aria-selected="false" aria-disabled="true" disabled', rendered)

    def test_flat_button_and_modal_omit_component_shadows(self):
        button = render_to_string(
            "components/button.html",
            {"text": "Save", "variant": "primary", "flat": True},
        )
        modal = render_to_string(
            "components/modal.html",
            {
                "modal_id": "flat-modal",
                "title": "Flat modal",
                "body": "Content",
                "flat": True,
            },
        )

        self.assertNotIn("shadow-", button)
        self.assertNotIn("shadow-[", modal)

    def test_modal_description_is_programmatically_associated(self):
        rendered = render_to_string(
            "components/modal.html",
            {
                "modal_id": "confirmation",
                "title": "Confirm action",
                "description": "Review this change.",
                "body": "This cannot be undone.",
            },
        )

        self.assertIn('aria-describedby="confirmation-description"', rendered)
        self.assertIn('id="confirmation-description"', rendered)
        self.assertIn("data-modal-backdrop", rendered)


class DashboardNavigationTests(TestCase):
    def test_shared_namespaces_match_only_the_configured_area(self):
        from uuid import UUID

        from apps.catalog.urls import urlpatterns as catalog_routes
        from apps.parties.urls import urlpatterns as party_routes
        from apps.purchasing.urls import urlpatterns as purchase_routes

        user = get_user_model().objects.create_superuser(username="navigation-admin")
        for namespace, routes in (
            ("catalog", catalog_routes),
            ("parties", party_routes),
            ("purchasing", purchase_routes),
        ):
            for route in routes:
                kwargs = {key: UUID(int=1) for key in route.pattern.converters}
                url = reverse(f"{namespace}:{route.name}", kwargs=kwargs)
                request = RequestFactory().get(url)
                request.user = user
                request.resolver_match = resolve(url)
                if namespace == "catalog":
                    expected = ["Medicines"]
                elif namespace == "purchasing":
                    expected = ["Purchases"]
                elif route.name.startswith("supplier-"):
                    expected = ["Suppliers"]
                elif route.name.startswith("customer-"):
                    expected = ["Customers"]
                else:
                    expected = []  # Prescribers has no sidebar entry.
                with self.subTest(route=route.name):
                    items = dashboard_navigation(request)["dashboard_navigation"]
                    self.assertEqual([item["label"] for item in items if item["is_active"]], expected)

    def test_unresolved_request_has_no_active_item(self):
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        request.resolver_match = None
        items = dashboard_navigation(request)["dashboard_navigation"]
        self.assertFalse(any(item["is_active"] for item in items))

    role_permissions = {
        "Owner / Admin": "all",
        "Pharmacist": {
            "catalog.view_medicine",
            "inventory.view_medicinebatch",
            "parties.view_customer",
            "prescriptions.view_prescription",
            "returns.view_customerreturn",
            "sales.view_salesinvoice",
        },
        "Inventory Manager": {
            "catalog.view_medicine",
            "inventory.view_medicinebatch",
            "parties.view_supplier",
            "purchasing.view_purchaseinvoice",
        },
        "Accountant": {
            "finance.view_financial_reports",
            "finance.view_customerpayment",
            "sales.view_salesinvoice",
        },
    }
    role_items = {
        "Owner / Admin": {
            "Dashboard",
            "Sales",
            "Medicines",
            "Inventory",
            "Suppliers",
            "Customers",
            "Prescriptions",
            "Purchases",
            "Invoices",
            "Payments",
            "Returns & Refunds",
            "Reports",
            "Settings",
            "Logout",
        },
        "Pharmacist": {
            "Dashboard",
            "Sales",
            "Medicines",
            "Inventory",
            "Customers",
            "Prescriptions",
            "Invoices",
            "Returns & Refunds",
            "Logout",
        },
        "Inventory Manager": {
            "Dashboard",
            "Medicines",
            "Inventory",
            "Suppliers",
            "Purchases",
            "Logout",
        },
        "Accountant": {
            "Dashboard",
            "Sales",
            "Invoices",
            "Payments",
            "Reports",
            "Logout",
        },
    }

    def navigation_for(self, role_name):
        group = Group.objects.create(name=role_name)
        user = get_user_model().objects.create_user(
            username=role_name.lower().replace(" ", "-").replace("/", ""),
            password="test-password",
        )
        user.groups.add(group)

        configured_permissions = self.role_permissions[role_name]
        if configured_permissions == "all":
            permissions = Permission.objects.all()
        else:
            permissions = [
                Permission.objects.get(
                    content_type__app_label=permission_name.split(".", 1)[0],
                    codename=permission_name.split(".", 1)[1],
                )
                for permission_name in configured_permissions
            ]
        group.permissions.add(*permissions)

        dashboard_url = reverse("dashboard:home")
        request = RequestFactory().get(dashboard_url)
        request.user = user
        request.resolver_match = resolve(dashboard_url)
        return dashboard_navigation(request)["dashboard_navigation"]

    def test_navigation_preserves_role_visibility(self):
        for role_name, expected_labels in self.role_items.items():
            with self.subTest(role=role_name):
                items = self.navigation_for(role_name)
                self.assertEqual({item["label"] for item in items}, expected_labels)

    def test_reports_navigation_requires_financial_report_permission(self):
        pharmacist_items = self.navigation_for("Pharmacist")
        accountant_items = self.navigation_for("Accountant")

        self.assertNotIn("Reports", {item["label"] for item in pharmacist_items})
        self.assertIn("Reports", {item["label"] for item in accountant_items})

    def test_dashboard_is_active_and_future_modules_are_disabled(self):
        items = self.navigation_for("Owner / Admin")
        dashboard = next(item for item in items if item["label"] == "Dashboard")
        medicines = next(item for item in items if item["label"] == "Medicines")
        suppliers = next(item for item in items if item["label"] == "Suppliers")
        customers = next(item for item in items if item["label"] == "Customers")
        purchases = next(item for item in items if item["label"] == "Purchases")
        settings = next(item for item in items if item["label"] == "Settings")
        future_items = [
            item
            for item in items
            if item["label"]
            not in {
                "Dashboard",
                "Medicines",
                "Suppliers",
                "Customers",
                "Purchases",
                "Payments",
                "Settings",
                "Logout",
            }
        ]

        self.assertTrue(dashboard["is_active"])
        self.assertEqual(dashboard["url"], "/dashboard/")
        self.assertEqual(medicines["url"], "/catalog/medicines/")
        self.assertEqual(suppliers["url"], "/parties/suppliers/")
        self.assertEqual(customers["url"], "/parties/customers/")
        self.assertEqual(purchases["url"], "/purchasing/invoices/")
        self.assertEqual(next(item for item in items if item["label"] == "Payments")["url"], "/finance/")
        self.assertEqual(settings["url"], "/settings/")
        self.assertTrue(all(item["url"] is None for item in future_items))

    def test_sections_and_post_logout_are_exposed_to_the_template(self):
        items = self.navigation_for("Owner / Admin")
        logout_item = next(item for item in items if item["label"] == "Logout")

        self.assertEqual(
            {item["section"] for item in items},
            {"Main", "Management", "Transactions", "Reports", "System"},
        )
        self.assertEqual(logout_item["url"], "/accounts/logout/")
        self.assertEqual(logout_item["method"], "post")


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dashboard-user",
            password="test-password",
        )
        self.dashboard_url = reverse("dashboard:home")

    def grant(self, *permission_names):
        permissions = []
        for permission_name in permission_names:
            app_label, codename = permission_name.split(".", 1)
            permissions.append(
                Permission.objects.get(
                    content_type__app_label=app_label,
                    codename=codename,
                )
            )
        self.user.user_permissions.add(*permissions)

    def test_dashboard_uses_the_single_canonical_route(self):
        self.assertEqual(self.dashboard_url, "/dashboard/")
        self.assertEqual(resolve(self.dashboard_url).view_name, "dashboard:home")
        self.assertRedirects(
            self.client.get("/"),
            reverse("accounts:login"),
            fetch_redirect_response=False,
        )

    def test_dashboard_requires_authentication(self):
        response = self.client.get(self.dashboard_url)

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={self.dashboard_url}",
        )

    def test_dashboard_replaces_the_component_preview(self):
        self.user.is_superuser = True
        self.user.is_staff = True
        self.user.save(update_fields=["is_superuser", "is_staff"])
        self.client.force_login(self.user)

        response = self.client.get(self.dashboard_url)

        self.assertEqual(response.context["breadcrumbs"], [{"label": "Dashboard"}])
        self.assertContains(response, "Clinical operations console")
        self.assertContains(response, "Daily Pulse")
        self.assertContains(response, "Active Medicines")
        self.assertContains(response, "Recent Activity")
        self.assertContains(response, "Attention Required")
        self.assertContains(response, "Operational ledger")
        self.assertContains(response, "Stock")
        self.assertContains(response, "Expiry")
        self.assertContains(response, "Operational Analytics")
        self.assertContains(response, 'aria-label="Breadcrumb"', html=False)
        self.assertContains(response, 'aria-current="page" title="Dashboard"', html=False)
        self.assertContains(response, "data-account-identity", html=False)
        self.assertContains(response, "dashboard-user")
        self.assertContains(response, "Staff member")
        self.assertNotContains(response, "Pharmacy operations")
        self.assertNotContains(response, "Dashboard UI foundation")
        self.assertNotContains(response, ">Demo<")
        self.assertNotContains(response, "Form controls")

    def test_dashboard_widgets_are_filtered_by_permissions(self):
        self.grant(
            "inventory.view_medicinebatch",
            "purchasing.view_purchaseinvoice",
        )
        self.client.force_login(self.user)

        response = self.client.get(self.dashboard_url)

        self.assertContains(response, "Low Stock")
        self.assertContains(response, "Expiring Soon")
        self.assertContains(response, "No recent activity is available.")
        self.assertNotContains(response, "Invoice PI-0298")
        self.assertNotContains(response, "Today&#x27;s Sales")
        self.assertNotContains(response, "Receivables")
        self.assertNotContains(response, "Customer payment")

    def test_dashboard_has_readable_empty_states_without_business_permissions(self):
        self.client.force_login(self.user)

        response = self.client.get(self.dashboard_url)

        self.assertContains(response, "No daily measures are available.")
        self.assertContains(response, "No recent activity is available.")
        self.assertContains(response, "No attention items are available.")
