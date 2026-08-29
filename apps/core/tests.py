from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase, TestCase

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
