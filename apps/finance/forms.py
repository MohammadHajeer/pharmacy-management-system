from decimal import Decimal

from django import forms
from django.utils import timezone

from .models import CustomerPayment, SupplierPayment

ZERO_MONEY = Decimal("0.00")


class _PaymentFormMixin:
    """Shared input validation for customer and supplier payment forms.

    Business-state rechecks (invoice status, outstanding balance) belong in
    ``apps.finance.services`` because they must run only after the invoice
    row has been locked; this mixin only validates the submitted values
    themselves.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.initial.get("paid_at"):
            self.initial["paid_at"] = timezone.now()

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None or amount <= ZERO_MONEY:
            raise forms.ValidationError("The payment amount must be greater than zero.")
        return amount

    def clean(self):
        cleaned_data = super().clean()
        payment_method = cleaned_data.get("payment_method")
        reference = (cleaned_data.get("reference") or "").strip()
        if payment_method is not None and payment_method.requires_reference and not reference:
            self.add_error(
                "reference",
                "The selected payment method requires a reference.",
            )
        return cleaned_data


class CustomerPaymentForm(_PaymentFormMixin, forms.ModelForm):
    """Validates a customer payment before ``services.post_customer_payment``."""

    class Meta:
        model = CustomerPayment
        fields = ("payment_method", "amount", "reference", "paid_at")


class SupplierPaymentForm(_PaymentFormMixin, forms.ModelForm):
    """Validates a supplier payment before ``services.post_supplier_payment``."""

    class Meta:
        model = SupplierPayment
        fields = ("payment_method", "amount", "reference", "paid_at")


class PaymentReversalForm(forms.Form):
    """Optional reversal metadata for ``services.reverse_*_payment``."""

    reversal_reason = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
