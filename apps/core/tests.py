from decimal import Decimal
from unittest.mock import patch
from uuid import UUID

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from config.navigation import DASHBOARD_NAVIGATION

from .document_numbers import (
    DocumentKind,
    customer_refund_number_for_creation,
    customer_return_number_for_creation,
    generate_document_number,
    purchase_invoice_number_for_posting,
    sales_invoice_number_for_completion,
    supplier_return_number_for_creation,
)
from .forms import PaymentMethodForm, PharmacySettingsForm, TaxRateForm
from .models import PaymentMethod, PharmacySettings, TaxRate
from .services import (
    process_payment_method_form,
    process_pharmacy_settings_form,
    process_tax_rate_form,
)


def pharmacy_settings_data(**overrides):
    data = {
        "pharmacy_name": "Community Pharmacy",
        "phone": "",
        "email": "",
        "address": "",
        "currency_code": "USD",
        "default_tax_rate": "",
        "expiry_warning_days": "90",
        "default_low_stock_threshold": "5.000",
        "invoice_header": "",
        "invoice_footer": "",
        "receipt_footer": "",
    }
    data.update(overrides)
    return data


class PharmacySettingsTests(SimpleTestCase):
    def test_string_representation_uses_pharmacy_name(self):
        settings = PharmacySettings(
            pharmacy_name="Community Pharmacy",
            currency_code="USD",
            default_low_stock_threshold=Decimal("0.000"),
        )

        self.assertEqual(str(settings), "Community Pharmacy")


class CoreSettingsFormTests(TestCase):
    def test_forms_expose_only_approved_operational_fields(self):
        self.assertEqual(
            tuple(PharmacySettingsForm().fields),
            (
                "pharmacy_name",
                "phone",
                "email",
                "address",
                "currency_code",
                "default_tax_rate",
                "expiry_warning_days",
                "default_low_stock_threshold",
                "invoice_header",
                "invoice_footer",
                "receipt_footer",
            ),
        )
        self.assertEqual(
            tuple(TaxRateForm().fields),
            ("code", "name", "rate_percent", "is_active"),
        )
        self.assertEqual(
            tuple(PaymentMethodForm().fields),
            ("code", "name", "requires_reference", "is_active"),
        )

    def test_currency_code_is_trimmed_and_normalized(self):
        form = PharmacySettingsForm(
            data=pharmacy_settings_data(currency_code="  usd  ")
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["currency_code"], "USD")

    def test_currency_code_requires_three_ascii_letters(self):
        for invalid_code in ("US", "US1", "U$D", "ÉUR"):
            with self.subTest(invalid_code=invalid_code):
                form = PharmacySettingsForm(
                    data=pharmacy_settings_data(currency_code=invalid_code)
                )

                self.assertFalse(form.is_valid())
                self.assertIn("currency_code", form.errors)

    def test_tax_rate_outside_approved_range_is_rejected(self):
        for invalid_rate in ("-0.0001", "100.0001"):
            with self.subTest(invalid_rate=invalid_rate):
                form = TaxRateForm(
                    data={
                        "code": "vat",
                        "name": "VAT",
                        "rate_percent": invalid_rate,
                        "is_active": "on",
                    }
                )

                self.assertFalse(form.is_valid())

    def test_negative_low_stock_threshold_is_rejected(self):
        form = PharmacySettingsForm(
            data=pharmacy_settings_data(default_low_stock_threshold="-0.001")
        )

        self.assertFalse(form.is_valid())

    def test_codes_are_normalized_without_restricting_future_codes(self):
        tax_form = TaxRateForm(
            data={
                "code": " reduced-5 ",
                "name": "Reduced",
                "rate_percent": "5.0000",
                "is_active": "on",
            }
        )
        payment_form = PaymentMethodForm(
            data={
                "code": " mobile_wallet ",
                "name": "Mobile wallet",
                "requires_reference": "on",
                "is_active": "on",
            }
        )

        self.assertTrue(tax_form.is_valid(), tax_form.errors)
        self.assertTrue(payment_form.is_valid(), payment_form.errors)
        self.assertEqual(tax_form.cleaned_data["code"], "REDUCED-5")
        self.assertEqual(payment_form.cleaned_data["code"], "MOBILE_WALLET")

    def test_payment_method_form_supports_deactivation(self):
        payment_method = PaymentMethod.objects.create(code="CARD", name="Card")
        form = PaymentMethodForm(
            data={
                "code": "CARD",
                "name": "Card",
                "requires_reference": "on",
            },
            instance=payment_method,
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["is_active"])


class CoreSettingsServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(username="settings-owner")
        cls.accountant = user_model.objects.create_user(username="settings-accountant")

        owner_group = Group.objects.create(name="Owner / Admin")
        accountant_group = Group.objects.create(name="Accountant")
        cls.owner.groups.add(owner_group)
        cls.accountant.groups.add(accountant_group)

        owner_group.permissions.set(
            Permission.objects.filter(
                content_type__app_label="core",
                codename__in={
                    "change_pharmacysettings",
                    "add_taxrate",
                    "change_taxrate",
                    "add_paymentmethod",
                    "change_paymentmethod",
                },
            )
        )

    def test_owner_group_permissions_create_and_update_one_settings_record(self):
        default_tax_rate = TaxRate.objects.create(
            code="VAT",
            name="VAT",
            rate_percent=Decimal("11.0000"),
        )
        create_form = process_pharmacy_settings_form(
            actor=self.owner,
            data=pharmacy_settings_data(
                currency_code="usd",
                default_tax_rate=str(default_tax_rate.id),
            ),
        )

        self.assertTrue(create_form.is_valid(), create_form.errors)
        self.assertEqual(PharmacySettings.objects.count(), 1)
        settings_id = create_form.instance.id
        self.assertEqual(create_form.instance.default_tax_rate, default_tax_rate)

        update_form = process_pharmacy_settings_form(
            actor=self.owner,
            data=pharmacy_settings_data(
                pharmacy_name="Updated Pharmacy",
                currency_code="eur",
                expiry_warning_days="30",
                default_low_stock_threshold="2.500",
            ),
        )

        self.assertTrue(update_form.is_valid(), update_form.errors)
        self.assertEqual(PharmacySettings.objects.count(), 1)
        self.assertEqual(update_form.instance.id, settings_id)
        self.assertEqual(update_form.instance.currency_code, "EUR")
        self.assertEqual(update_form.instance.expiry_warning_days, 30)
        self.assertEqual(
            update_form.instance.default_low_stock_threshold,
            Decimal("2.500"),
        )

    def test_invalid_settings_form_does_not_create_or_update(self):
        settings = PharmacySettings.objects.create(
            pharmacy_name="Original Pharmacy",
            currency_code="USD",
        )

        form = process_pharmacy_settings_form(
            actor=self.owner,
            data=pharmacy_settings_data(
                pharmacy_name="Invalid Update",
                currency_code="US1",
            ),
        )

        self.assertFalse(form.is_valid())
        settings.refresh_from_db()
        self.assertEqual(settings.pharmacy_name, "Original Pharmacy")
        self.assertEqual(PharmacySettings.objects.count(), 1)

    def test_anonymous_and_unauthorized_callers_are_denied(self):
        service_calls = (
            lambda actor: process_pharmacy_settings_form(
                actor=actor,
                data=pharmacy_settings_data(),
            ),
            lambda actor: process_tax_rate_form(
                actor=actor,
                data={
                    "code": "VAT",
                    "name": "VAT",
                    "rate_percent": "11.0000",
                    "is_active": "on",
                },
            ),
            lambda actor: process_payment_method_form(
                actor=actor,
                data={
                    "code": "CASH",
                    "name": "Cash",
                    "is_active": "on",
                },
            ),
        )

        for actor in (AnonymousUser(), self.accountant):
            for call_service in service_calls:
                with self.subTest(actor=actor, service=call_service):
                    with self.assertRaises(PermissionDenied):
                        call_service(actor)

        self.assertFalse(PharmacySettings.objects.exists())
        self.assertFalse(TaxRate.objects.exists())
        self.assertFalse(PaymentMethod.objects.exists())

    def test_owner_can_create_and_update_tax_rate(self):
        create_form = process_tax_rate_form(
            actor=self.owner,
            data={
                "code": "vat",
                "name": "VAT",
                "rate_percent": "11.0000",
                "is_active": "on",
            },
        )

        self.assertTrue(create_form.is_valid(), create_form.errors)
        self.assertEqual(create_form.instance.code, "VAT")

        update_form = process_tax_rate_form(
            actor=self.owner,
            instance=create_form.instance,
            data={
                "code": "vat",
                "name": "VAT updated",
                "rate_percent": "10.0000",
            },
        )

        self.assertTrue(update_form.is_valid(), update_form.errors)
        create_form.instance.refresh_from_db()
        self.assertEqual(create_form.instance.name, "VAT updated")
        self.assertFalse(create_form.instance.is_active)

    def test_owner_can_create_and_deactivate_payment_method(self):
        create_form = process_payment_method_form(
            actor=self.owner,
            data={
                "code": "card",
                "name": "Card",
                "requires_reference": "on",
                "is_active": "on",
            },
        )

        self.assertTrue(create_form.is_valid(), create_form.errors)
        self.assertTrue(create_form.instance.is_active)

        update_form = process_payment_method_form(
            actor=self.owner,
            instance=create_form.instance,
            data={
                "code": "card",
                "name": "Card",
                "requires_reference": "on",
            },
        )

        self.assertTrue(update_form.is_valid(), update_form.errors)
        create_form.instance.refresh_from_db()
        self.assertFalse(create_form.instance.is_active)

    def test_add_permission_does_not_authorize_an_update(self):
        user = get_user_model().objects.create_user(username="settings-add-only")
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename="add_paymentmethod",
            )
        )
        payment_method = PaymentMethod.objects.create(code="CASH", name="Cash")

        create_form = process_payment_method_form(
            actor=user,
            data={
                "code": "CARD",
                "name": "Card",
                "is_active": "on",
            },
        )

        self.assertTrue(create_form.is_valid(), create_form.errors)
        with self.assertRaises(PermissionDenied):
            process_payment_method_form(
                actor=user,
                instance=payment_method,
                data={
                    "code": "CASH",
                    "name": "Cash updated",
                    "is_active": "on",
                },
            )


class CoreSettingsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.owner = user_model.objects.create_user(username="settings-ui-owner")
        cls.unauthorized_user = user_model.objects.create_user(
            username="settings-ui-accountant"
        )
        cls.add_only_user = user_model.objects.create_user(
            username="settings-ui-add-only"
        )

        owner_group = Group.objects.create(name="Owner / Admin")
        owner_group.permissions.set(
            Permission.objects.filter(
                content_type__app_label="core",
                codename__in={
                    "change_pharmacysettings",
                    "add_taxrate",
                    "change_taxrate",
                    "add_paymentmethod",
                    "change_paymentmethod",
                },
            )
        )
        cls.owner.groups.add(owner_group)
        cls.add_only_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="core",
                codename="add_taxrate",
            )
        )

    def setUp(self):
        self.client.force_login(self.owner)

    def test_authorized_user_can_view_operational_settings(self):
        TaxRate.objects.create(code="VAT", name="VAT", rate_percent="11.0000")
        PaymentMethod.objects.create(code="CASH", name="Cash")

        response = self.client.get(reverse("core:settings"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pharmacy information")
        self.assertContains(response, "Business configuration")
        self.assertContains(response, "Tax rates")
        self.assertContains(response, "Payment methods")
        self.assertContains(response, "Invoice and receipt text")
        self.assertContains(response, 'placeholder="Enter pharmacy name"', html=False)
        self.assertContains(response, 'placeholder="Enter phone number"', html=False)
        self.assertContains(response, 'placeholder="Enter contact email"', html=False)
        self.assertContains(response, 'placeholder="Enter pharmacy address"', html=False)
        self.assertContains(response, "VAT")
        self.assertContains(response, "Cash")
        self.assertContains(response, 'name="default_tax_rate"', html=False)
        self.assertContains(response, "data-custom-select-native", html=False)
        self.assertContains(response, "data-custom-select-trigger", html=False)
        self.assertContains(response, "data-dirty-form")
        self.assertContains(response, "data-dirty-submit")
        self.assertContains(response, "data-dirty-indicator")
        self.assertContains(response, "data-pristine-indicator")
        self.assertContains(response, "data-dirty-surface")
        self.assertContains(response, 'href="#pharmacy-information"', html=False)
        self.assertContains(response, "Rate / code")
        self.assertContains(response, "Identifier")
        self.assertRegex(
            response.content.decode(),
            r'<button type="submit" disabled[^>]+data-dirty-submit',
        )
        self.assertContains(response, 'data-modal-open="tax-rate-create"')
        self.assertContains(response, 'data-modal-open="payment-method-create"')
        self.assertContains(
            response,
            'id="tax-rate-create-is-active"',
            html=False,
        )
        self.assertContains(
            response,
            'id="payment-method-create-requires-reference"',
            html=False,
        )
        self.assertContains(
            response,
            'id="payment-method-create-is-active"',
            html=False,
        )

    def test_anonymous_and_unauthorized_users_cannot_access_settings(self):
        self.client.logout()
        response = self.client.get(reverse("core:settings"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

        self.client.force_login(self.unauthorized_user)
        response = self.client.get(reverse("core:settings"))
        self.assertEqual(response.status_code, 403)

    def test_valid_settings_post_uses_service_and_redirects(self):
        with patch(
            "apps.core.views.process_pharmacy_settings_form",
            wraps=process_pharmacy_settings_form,
        ) as service:
            response = self.client.post(
                reverse("core:settings"),
                pharmacy_settings_data(pharmacy_name="PHARMANEX Central"),
            )

        self.assertRedirects(response, reverse("core:settings"))
        self.assertEqual(service.call_count, 1)
        self.assertEqual(
            PharmacySettings.objects.get(singleton_key=1).pharmacy_name,
            "PHARMANEX Central",
        )

    def test_invalid_settings_post_preserves_values_and_errors(self):
        response = self.client.post(
            reverse("core:settings"),
            pharmacy_settings_data(
                pharmacy_name="Entered Pharmacy",
                currency_code="US1",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].is_bound)
        self.assertIn("currency_code", response.context["form"].errors)
        self.assertContains(response, 'value="Entered Pharmacy"', html=False)
        self.assertContains(response, 'value="US1"', html=False)
        self.assertFalse(PharmacySettings.objects.exists())

    @override_settings(SECRET_KEY="ui-test-secret-that-must-never-render")
    def test_settings_page_does_not_render_deployment_secrets(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:settings"))

        self.assertNotContains(response, "ui-test-secret-that-must-never-render")
        self.assertNotContains(response, "DATABASE_URL")
        self.assertNotContains(response, "SECRET_KEY")
        self.assertNotContains(response, "API_KEY")

    def test_tax_rate_create_and_edit_use_permission_specific_routes(self):
        create_response = self.client.post(
            reverse("core:tax-rate-create"),
            {
                "code": "vat",
                "name": "VAT",
                "rate_percent": "11.0000",
                "is_active": "on",
            },
        )
        tax_rate = TaxRate.objects.get(code="VAT")
        self.assertRedirects(create_response, reverse("core:settings"))

        self.client.force_login(self.add_only_user)
        edit_response = self.client.post(
            reverse("core:tax-rate-edit", args=[tax_rate.pk]),
            {
                "code": "VAT",
                "name": "Changed without permission",
                "rate_percent": "10.0000",
                "is_active": "on",
            },
        )
        self.assertEqual(edit_response.status_code, 403)
        tax_rate.refresh_from_db()
        self.assertEqual(tax_rate.name, "VAT")

    def test_invalid_tax_rate_post_reopens_modal_with_bound_errors(self):
        TaxRate.objects.create(code="VAT", name="VAT", rate_percent="11.0000")

        response = self.client.post(
            reverse("core:tax-rate-create"),
            {
                "code": "VAT",
                "name": "Entered duplicate",
                "rate_percent": "5.0000",
                "is_active": "on",
            },
        )

        modal_form = response.context["tax_rate_create_form"]
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/settings/index.html")
        self.assertEqual(response.context["open_modal"], "tax-rate-create")
        self.assertTrue(modal_form.is_bound)
        self.assertIn("code", modal_form.errors)
        self.assertContains(response, 'data-modal-open-on-load', html=False)
        self.assertContains(response, 'value="Entered duplicate"', html=False)

    def test_invalid_tax_rate_edit_reopens_matching_modal(self):
        tax_rate = TaxRate.objects.create(
            code="VAT",
            name="VAT",
            rate_percent="11.0000",
        )

        response = self.client.post(
            reverse("core:tax-rate-edit", args=[tax_rate.pk]),
            {
                "code": "VAT",
                "name": "Entered edit",
                "rate_percent": "101.0000",
                "is_active": "on",
            },
        )

        modal_id = f"tax-rate-edit-{tax_rate.pk}"
        matching_row = next(
            row
            for row in response.context["tax_rate_rows"]
            if row["object"].pk == tax_rate.pk
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/settings/index.html")
        self.assertEqual(response.context["open_modal"], modal_id)
        self.assertTrue(matching_row["form"].is_bound)
        self.assertIn("__all__", matching_row["form"].errors)
        self.assertContains(response, f'id="{modal_id}"', html=False)
        self.assertContains(response, "data-modal-open-on-load", html=False)

    def test_modal_forms_submit_with_csrf_protection_enabled(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        settings_response = csrf_client.get(reverse("core:settings"))
        csrf_token = csrf_client.cookies["csrftoken"].value

        response = csrf_client.post(
            reverse("core:tax-rate-create"),
            {
                "csrfmiddlewaretoken": csrf_token,
                "code": "VAT",
                "name": "VAT",
                "rate_percent": "11.0000",
                "is_active": "on",
            },
        )

        self.assertEqual(settings_response.status_code, 200)
        self.assertRedirects(response, reverse("core:settings"))
        self.assertTrue(TaxRate.objects.filter(code="VAT").exists())

    def test_invalid_payment_method_post_preserves_values(self):
        PaymentMethod.objects.create(code="CASH", name="Cash")

        response = self.client.post(
            reverse("core:payment-method-create"),
            {
                "code": "CASH",
                "name": "Entered duplicate",
                "requires_reference": "on",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        modal_form = response.context["payment_method_create_form"]
        self.assertTemplateUsed(response, "core/settings/index.html")
        self.assertEqual(response.context["open_modal"], "payment-method-create")
        self.assertTrue(modal_form.is_bound)
        self.assertIn("code", modal_form.errors)
        self.assertContains(response, "data-modal-open-on-load", html=False)
        self.assertContains(response, 'value="Entered duplicate"', html=False)
        self.assertContains(response, "Payment method with this Code already exists")

    def test_valid_payment_method_post_redirects_to_settings(self):
        response = self.client.post(
            reverse("core:payment-method-create"),
            {
                "code": "CARD",
                "name": "Card",
                "requires_reference": "on",
                "is_active": "on",
            },
        )

        self.assertRedirects(response, reverse("core:settings"))
        self.assertTrue(
            PaymentMethod.objects.filter(
                code="CARD",
                name="Card",
                requires_reference=True,
            ).exists()
        )

    def test_payment_method_actions_require_their_existing_permissions(self):
        payment_method = PaymentMethod.objects.create(code="CASH", name="Cash")
        self.client.force_login(self.unauthorized_user)

        create_response = self.client.post(
            reverse("core:payment-method-create"),
            {"code": "CARD", "name": "Card", "is_active": "on"},
        )
        edit_response = self.client.post(
            reverse("core:payment-method-edit", args=[payment_method.pk]),
            {"code": "CASH", "name": "Changed", "is_active": "on"},
        )

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(edit_response.status_code, 403)
        self.assertFalse(PaymentMethod.objects.filter(code="CARD").exists())
        payment_method.refresh_from_db()
        self.assertEqual(payment_method.name, "Cash")

    def test_navigation_uses_the_core_settings_route_and_permission(self):
        settings_item = next(
            item for item in DASHBOARD_NAVIGATION if item["label"] == "Settings"
        )

        self.assertEqual(settings_item["url_name"], "core:settings")
        self.assertEqual(settings_item["namespace"], "core")
        self.assertEqual(settings_item["permission"], "core.change_pharmacysettings")


class DocumentNumberTests(SimpleTestCase):
    document_id = UUID("abcdefab-cdef-abcd-efab-cdefabcdefab")

    def test_every_lifecycle_wrapper_uses_approved_full_uuid_format(self):
        cases = (
            (
                DocumentKind.SALES_INVOICE,
                sales_invoice_number_for_completion,
                "SAL",
            ),
            (
                DocumentKind.PURCHASE_INVOICE,
                purchase_invoice_number_for_posting,
                "PUR",
            ),
            (
                DocumentKind.CUSTOMER_RETURN,
                customer_return_number_for_creation,
                "CRT",
            ),
            (
                DocumentKind.SUPPLIER_RETURN,
                supplier_return_number_for_creation,
                "SRT",
            ),
            (
                DocumentKind.CUSTOMER_REFUND,
                customer_refund_number_for_creation,
                "CRF",
            ),
        )

        for kind, wrapper, prefix in cases:
            with self.subTest(kind=kind):
                expected = f"{prefix}-{self.document_id.hex.upper()}"
                self.assertEqual(
                    generate_document_number(self.document_id, kind),
                    expected,
                )
                self.assertEqual(wrapper(self.document_id), expected)
                self.assertEqual(len(expected), 36)
                self.assertEqual(expected, expected.upper())

    def test_generation_is_retry_safe_and_uuid_specific(self):
        first = sales_invoice_number_for_completion(self.document_id)

        self.assertEqual(
            first,
            sales_invoice_number_for_completion(self.document_id),
        )
        self.assertNotEqual(
            first,
            sales_invoice_number_for_completion(
                UUID("00000000-0000-0000-0000-000000000001")
            ),
        )

    def test_invalid_uuid_and_document_kind_are_rejected(self):
        with self.assertRaisesRegex(TypeError, "document_id must be a UUID"):
            generate_document_number(str(self.document_id), DocumentKind.SALES_INVOICE)

        with self.assertRaisesRegex(TypeError, "kind must be a DocumentKind"):
            generate_document_number(self.document_id, "sales_invoice")

    def test_generated_numbers_fit_every_existing_document_field(self):
        from apps.purchasing.models import PurchaseInvoice
        from apps.returns.models import CustomerRefund, CustomerReturn, SupplierReturn
        from apps.sales.models import SalesInvoice

        document_fields = (
            (SalesInvoice, "invoice_number"),
            (PurchaseInvoice, "invoice_number"),
            (CustomerReturn, "return_number"),
            (SupplierReturn, "return_number"),
            (CustomerRefund, "refund_number"),
        )

        for model, field_name in document_fields:
            with self.subTest(model=model.__name__):
                field = model._meta.get_field(field_name)
                self.assertEqual(field.max_length, 40)
                self.assertLessEqual(36, field.max_length)

        self.assertIn(
            "sales_completed_invoice_number_unique",
            {constraint.name for constraint in SalesInvoice._meta.constraints},
        )
        self.assertIn(
            "purchasing_posted_invoice_number_unique",
            {constraint.name for constraint in PurchaseInvoice._meta.constraints},
        )

    def test_sales_and_purchase_numbers_remain_blank_for_new_drafts(self):
        from apps.purchasing.models import PurchaseInvoice
        from apps.sales.models import SalesInvoice

        for model in (SalesInvoice, PurchaseInvoice):
            with self.subTest(model=model.__name__):
                field = model._meta.get_field("invoice_number")
                self.assertTrue(field.blank)
                self.assertEqual(field.get_default(), "")

    def test_return_and_refund_numbers_are_required_and_unique(self):
        from apps.returns.models import CustomerRefund, CustomerReturn, SupplierReturn

        for model, field_name in (
            (CustomerReturn, "return_number"),
            (SupplierReturn, "return_number"),
            (CustomerRefund, "refund_number"),
        ):
            with self.subTest(model=model.__name__):
                field = model._meta.get_field(field_name)
                self.assertFalse(field.blank)
                self.assertTrue(field.unique)
