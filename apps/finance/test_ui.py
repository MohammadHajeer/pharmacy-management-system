from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.models import PharmacySettings
from apps.parties.models import Customer, Supplier

from . import services
from .models import CustomerPayment, PaymentStatus, SupplierPayment
from .tests import _FinanceFixtureMixin


class _PaymentViewTests(_FinanceFixtureMixin):
    @classmethod
    def setUpTestData(cls):
        cls._build_fixtures()
        cls.finance_user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="finance",
            codename__in=["view_customerpayment", "view_supplierpayment"],
        ))
        PharmacySettings.objects.create(pharmacy_name="Test pharmacy", currency_code="EUR")

    def setUp(self):
        self.client.force_login(self.finance_user)
        self.invoice = self.sales_invoice if self.kind == "customer" else self.purchase_invoice
        self.invoice_field = "sales_invoice" if self.kind == "customer" else "purchase_invoice"
        self.balance_field = "balance_due" if self.kind == "customer" else "remaining_balance"
        self.model = CustomerPayment if self.kind == "customer" else SupplierPayment

    def url(self, action, pk=None):
        return reverse(f"finance:{self.kind}-{action}", kwargs={"pk": pk} if pk else None)

    def data(self, **overrides):
        return {
            "amount": "40.00", "payment_method": str(self.payment_method.pk),
            "paid_at": "2026-08-30T10:15:00", "reference": "TEST-REF", **overrides,
        }

    def post_payment(self, **overrides):
        service = getattr(services, f"post_{self.kind}_payment")
        form, payment = service(
            actor=self.finance_user, data=self.data(**overrides),
            **{self.invoice_field: self.invoice},
        )
        self.assertFalse(form.errors)
        return payment

    def grant(self, user, *codenames):
        user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="finance", codename__in=codenames,
        ))

    def test_anonymous_and_unauthorized_access_to_every_route(self):
        payment = self.post_payment()
        routes = [
            ("payment-list", None, "get"), ("payment-create", None, "get"),
            ("payment-record", self.invoice.pk, "get"),
            ("payment-record", self.invoice.pk, "post"),
            ("invoice-detail", self.invoice.pk, "get"),
            ("payment-detail", payment.pk, "get"),
            ("payment-reverse", payment.pk, "post"),
        ]
        for user, expected in ((None, 302), (self.unauthorized_user, 403)):
            self.client.logout()
            if user:
                self.client.force_login(user)
            for action, pk, method in routes:
                with self.subTest(user=user, action=action, method=method):
                    response = getattr(self.client, method)(self.url(action, pk))
                    self.assertEqual(response.status_code, expected)
                    if not user:
                        self.assertIn(reverse("accounts:login"), response.url)

    def test_authorized_list_detail_context_and_flat_navigation(self):
        payment = self.post_payment()
        response = self.client.get(self.url("payment-list"))
        self.assertContains(response, f"{self.kind.title()} payment ledger")
        self.assertContains(response, "TEST-REF")
        self.assertContains(response, "workspace-container")
        self.assertContains(response, 'class="relative ledger-scroll"')
        self.assertContains(response, "data-registry-filter-form")
        self.assertContains(response, "data-custom-select")
        self.assertContains(response, 'aria-current="page"')
        self.assertEqual(len(response.context["rows"]), 1)
        sidebar = [item for item in response.context["dashboard_navigation"] if item["label"] == "Payments"]
        self.assertTrue(sidebar[0]["is_active"])
        response = self.client.get(self.url("payment-detail", payment.pk))
        self.assertContains(response, "Payment summary")
        self.assertContains(response, str(payment.pk))
        self.assertContains(response, "Invoice financial context")
        self.assertContains(response, "Already paid")

    def test_empty_and_filtered_empty_states(self):
        self.assertContains(self.client.get(self.url("payment-list")), f"No {self.kind} payments yet")
        response = self.client.get(self.url("payment-list"), {"q": "unmatched"})
        self.assertContains(response, "No payments match the current filters.")
        self.assertContains(response, "Clear filters")

    def test_post_success_uses_service_and_ignores_forged_party_and_actor(self):
        party_model = Customer if self.kind == "customer" else Supplier
        wrong_party = party_model.objects.create(code="OTHER", name="Other party")
        response = self.client.post(self.url("payment-record", self.invoice.pk), self.data(**{
            self.kind: str(wrong_party.pk), "processed_by": self.unauthorized_user.pk,
            "status": "REVERSED", "paid_total": "99999.00",
        }))
        payment = self.model.objects.get()
        self.assertRedirects(response, self.url("payment-detail", payment.pk))
        self.assertEqual(getattr(payment, f"{self.kind}_id"), getattr(self.invoice, f"{self.kind}_id"))
        self.assertEqual(payment.processed_by, self.finance_user)
        self.assertEqual(payment.status, PaymentStatus.POSTED)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_total, Decimal("40.00"))
        self.assertEqual(self.invoice.payment_status, "PARTIAL")

    def test_post_permission_alone_is_sufficient_and_redirect_is_accessible(self):
        self.grant(self.unauthorized_user, f"post_{self.kind}payment")
        self.client.force_login(self.unauthorized_user)
        self.assertEqual(self.client.get(self.url("payment-create")).status_code, 200)
        response = self.client.post(self.url("payment-record", self.invoice.pk), self.data())
        self.assertRedirects(response, self.url("payment-create"))
        payment = self.model.objects.get()
        response = self.client.post(self.url("payment-reverse", payment.pk), {})
        self.assertRedirects(response, self.url("payment-create"))

    def test_add_change_and_view_permissions_do_not_allow_post_or_reverse(self):
        payment = self.post_payment()
        self.grant(self.unauthorized_user, f"view_{self.kind}payment", f"add_{self.kind}payment", f"change_{self.kind}payment")
        self.client.force_login(self.unauthorized_user)
        response = self.client.get(self.url("payment-detail", payment.pk))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Reverse payment")
        self.assertNotContains(self.client.get(self.url("payment-list")), "Record payment")
        self.assertEqual(self.client.post(self.url("payment-record", self.invoice.pk), self.data()).status_code, 403)
        self.assertEqual(self.client.post(self.url("payment-reverse", payment.pk), {}).status_code, 403)
        self.assertEqual(self.model.objects.get().status, PaymentStatus.POSTED)

    def test_validation_retains_inputs_and_reference_requirement(self):
        response = self.client.post(self.url("payment-record", self.invoice.pk), self.data(
            payment_method=str(self.reference_payment_method.pk), reference="",
        ))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The selected payment method requires a reference.")
        self.assertContains(response, 'value="40.00"')
        self.assertContains(response, 'value="2026-08-30T10:15:00"')
        self.assertContains(response, "— reference required")
        self.assertEqual(response.context["form"]["payment_method"].value(), str(self.reference_payment_method.pk))
        self.assertFalse(self.model.objects.exists())

    def test_invalid_timestamp_and_inactive_method_are_field_errors(self):
        self.payment_method.is_active = False
        self.payment_method.save(update_fields=["is_active"])
        response = self.client.post(self.url("payment-record", self.invoice.pk), self.data(paid_at="not-a-date"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("paid_at", response.context["form"].errors)
        self.assertIn("payment_method", response.context["form"].errors)
        self.assertFalse(self.model.objects.exists())

    def test_overpayment_surfaces_service_error_without_writing(self):
        self.post_payment()
        response = self.client.post(self.url("payment-record", self.invoice.pk), self.data(amount="999.00"))
        self.assertContains(response, "cannot exceed the outstanding balance")
        self.assertContains(response, 'value="999.00"')
        self.assertEqual(self.model.objects.count(), 1)
        self.assertEqual(response.context["balance"], self.invoice.grand_total - Decimal("40.00"))

    def test_ineligible_invoice_hides_action_and_service_rejects_post(self):
        self.invoice.status = "DRAFT"
        self.invoice.save(update_fields=["status"])
        response = self.client.get(self.url("payment-record", self.invoice.pk))
        self.assertNotContains(response, '>Post payment<')
        response = self.client.post(self.url("payment-record", self.invoice.pk), self.data())
        self.assertContains(response, "Payments can only be posted against")
        self.assertTrue(response.context["form"].non_field_errors())
        self.assertFalse(self.model.objects.exists())

    def test_invoice_action_and_chooser_follow_state_balance_and_permission(self):
        response = self.client.get(self.url("invoice-detail", self.invoice.pk))
        self.assertContains(response, self.url("payment-record", self.invoice.pk))
        self.assertContains(self.client.get(self.url("payment-create")), self.invoice.invoice_number)
        self.post_payment(amount=str(self.invoice.grand_total))
        response = self.client.get(self.url("invoice-detail", self.invoice.pk))
        self.assertNotContains(response, self.url("payment-record", self.invoice.pk))
        self.assertContains(response, "Paid")
        self.assertContains(self.client.get(self.url("payment-create")), "No invoices available for payment")
        self.grant(self.unauthorized_user, f"view_{self.kind}payment")
        self.client.force_login(self.unauthorized_user)
        response = self.client.get(self.url("invoice-detail", self.invoice.pk))
        self.assertNotContains(response, "Record payment")

    def test_chooser_search_and_invoice_scoped_history(self):
        payment = self.post_payment()
        self.assertContains(self.client.get(self.url("payment-create")), 'class="relative ledger-scroll"')
        response = self.client.get(self.url("payment-create"), {"q": "unmatched"})
        self.assertContains(response, "No invoices match this search")
        response = self.client.get(self.url("invoice-detail", self.invoice.pk))
        self.assertEqual([row["payment"].pk for row in response.context["rows"]], [payment.pk])

    def test_reversal_confirmation_success_and_retained_history(self):
        payment = self.post_payment()
        response = self.client.get(self.url("payment-detail", payment.pk))
        self.assertContains(response, 'role="dialog"')
        self.assertContains(response, "Reason (optional)")
        self.assertContains(response, "will remain in the financial history")
        response = self.client.post(self.url("payment-reverse", payment.pk), {"reversal_reason": "Duplicate transfer"})
        self.assertRedirects(response, self.url("payment-detail", payment.pk))
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.REVERSED)
        self.assertEqual(payment.reversed_by, self.finance_user)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_total, Decimal("0.00"))
        response = self.client.get(self.url("payment-detail", payment.pk))
        self.assertContains(response, "Duplicate transfer")
        self.assertContains(response, "Reversed by")
        self.assertContains(response, "40.00")
        self.assertNotContains(response, "Reverse payment?")
        self.assertContains(self.client.get(self.url("payment-list")), "Reversed")

    def test_reversal_error_reopens_dialog_and_retains_reason(self):
        payment = self.post_payment()
        response = self.client.post(self.url("payment-reverse", payment.pk), {"reversal_reason": "x" * 2001})
        self.assertContains(response, "data-modal-open-on-load")
        self.assertContains(response, "x" * 2001)
        self.assertTrue(response.context["reversal_form"].errors)
        self.client.post(self.url("payment-reverse", payment.pk), {})
        response = self.client.post(self.url("payment-reverse", payment.pk), {"reversal_reason": "Retried"})
        self.assertContains(response, "Only a posted payment can be reversed.")
        self.assertContains(response, "data-modal-open-on-load")
        self.assertEqual(self.model.objects.count(), 1)

    def test_reads_do_not_mutate_and_csrf_is_required(self):
        payment = self.post_payment()
        self.assertEqual(self.client.get(self.url("payment-reverse", payment.pk)).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.finance_user)
        self.assertEqual(client.post(self.url("payment-reverse", payment.pk), {}).status_code, 403)
        self.assertEqual(client.post(self.url("payment-record", self.invoice.pk), self.data()).status_code, 403)
        self.assertEqual(self.model.objects.get().status, PaymentStatus.POSTED)

    def test_search_status_method_and_malformed_filters(self):
        payment = self.post_payment()
        other = self.post_payment(payment_method=str(self.reference_payment_method.pk), reference="BANK-REF")
        getattr(services, f"reverse_{self.kind}_payment")(actor=self.finance_user, payment=other)
        for filters in (
            {"q": "TEST-REF"}, {"q": self.invoice.invoice_number, "status": "POSTED"},
            {"q": getattr(self.invoice, self.kind).name, "method": str(self.payment_method.pk)},
        ):
            with self.subTest(filters=filters):
                response = self.client.get(self.url("payment-list"), filters)
                self.assertEqual([row["payment"].pk for row in response.context["rows"]], [payment.pk])
        response = self.client.get(self.url("payment-list"), {"status": "REVERSED"})
        self.assertEqual(response.context["rows"][0]["payment"].pk, other.pk)
        for filters in ({"method": "bad"}, {"method": str(uuid4())}, {"status": "DRAFT"}):
            response = self.client.get(self.url("payment-list"), filters)
            self.assertContains(response, "A filter is invalid")
            self.assertEqual(response.context["page_obj"].paginator.count, 0)
        self.payment_method.is_active = False
        self.payment_method.save(update_fields=["is_active"])
        response = self.client.get(self.url("payment-list"), {"method": str(self.payment_method.pk)})
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_pagination_is_stable_and_preserves_filters(self):
        now = timezone.now()
        self.model.objects.bulk_create([
            self.model(**{
                self.invoice_field: self.invoice, self.kind: getattr(self.invoice, self.kind),
                "payment_method": self.payment_method, "amount": Decimal("1.00"),
                "processed_by": self.finance_user, "paid_at": now, "reference": "PAGE",
            }) for _ in range(27)
        ])
        filters = {"q": "PAGE", "status": "POSTED", "method": str(self.payment_method.pk), "extra": "keep"}
        response = self.client.get(self.url("payment-list"), filters)
        self.assertEqual(len(response.context["rows"]), 25)
        self.assertContains(response, "page=2")
        self.assertContains(response, "extra=keep")
        self.assertContains(response, f"method={self.payment_method.pk}")
        self.assertContains(response, "status=POSTED")
        self.assertContains(response, "q=PAGE")
        first = [row["payment"].pk for row in response.context["rows"]]
        response = self.client.get(self.url("payment-list"), {**filters, "page": 2})
        second = [row["payment"].pk for row in response.context["rows"]]
        expected = list(self.model.objects.order_by("-paid_at", "-id").values_list("pk", flat=True))
        self.assertEqual(first + second, expected)
        for value, expected_page in (("bad", 1), ("999", 2), ("-1", 2)):
            response = self.client.get(self.url("payment-list"), {"page": value})
            self.assertEqual(response.context["page_obj"].number, expected_page)

    def test_currency_uses_configured_fallback_without_relabelling_historical_invoice(self):
        response = self.client.get(self.url("payment-record", self.invoice.pk))
        self.assertEqual(response.context["currency_code"], "EUR")
        self.assertContains(response, "USD")  # Existing invoice currency snapshot wins.
        self.invoice.currency_code = "EUR"
        self.invoice.save(update_fields=["currency_code"])
        response = self.client.get(self.url("payment-record", self.invoice.pk))
        self.assertContains(response, "EUR")
        self.assertNotContains(response, "USD")
        self.assertNotContains(response, "$1")

    def test_missing_records_return_404(self):
        for action in ("payment-record", "payment-detail", "invoice-detail"):
            self.assertEqual(self.client.get(self.url(action, uuid4())).status_code, 404)


class CustomerPaymentViewTests(_PaymentViewTests, TestCase):
    kind = "customer"

    def test_walk_in_reversal_business_error_is_visible(self):
        payment = self.post_payment(amount="100.00")
        self.invoice.customer = None
        self.invoice.save(update_fields=["customer"])
        payment.customer = None
        payment.save(update_fields=["customer"])
        response = self.client.post(self.url("payment-reverse", payment.pk), {"reversal_reason": "Mistake"})
        self.assertContains(response, "walk-in sale with an outstanding balance")
        self.assertContains(response, "data-modal-open-on-load")
        self.assertContains(response, "Mistake")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.POSTED)


class SupplierPaymentViewTests(_PaymentViewTests, TestCase):
    kind = "supplier"

    def test_supplier_only_user_has_payments_navigation_without_customer_access(self):
        self.grant(self.unauthorized_user, "view_supplierpayment")
        self.client.force_login(self.unauthorized_user)
        response = self.client.get(reverse("finance:payment-list"))
        self.assertRedirects(response, self.url("payment-list"))
        response = self.client.get(self.url("payment-list"))
        self.assertContains(response, reverse("finance:payment-list"))
        self.assertNotContains(response, reverse("finance:customer-payment-list"))
        self.assertEqual(self.client.get(reverse("finance:customer-payment-list")).status_code, 403)

    def test_purchase_invoice_action_visibility(self):
        self.finance_user.user_permissions.add(Permission.objects.get(
            content_type__app_label="purchasing", codename="view_purchaseinvoice",
        ))
        detail_url = reverse("purchasing:purchase-invoice-detail", kwargs={"pk": self.invoice.pk})
        self.assertContains(self.client.get(detail_url), "Record supplier payment")
        self.post_payment(amount="200.00")
        response = self.client.get(detail_url)
        self.assertNotContains(response, "Record supplier payment")
        self.assertContains(response, "Payment history")
        self.invoice.status = "DRAFT"
        self.invoice.save(update_fields=["status"])
        self.assertNotContains(self.client.get(detail_url), "Record supplier payment")


class PaymentHomeTests(TestCase):
    def test_home_requires_login_and_a_payment_view_permission(self):
        url = reverse("finance:payment-list")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(get_user_model().objects.create_user(username="no-finance"))
        self.assertEqual(self.client.get(url).status_code, 403)
