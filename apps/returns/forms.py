from decimal import Decimal

from django import forms
from django.utils import timezone

from apps.core.models import PaymentMethod
from apps.inventory.models import MedicineBatch
from apps.sales.models import SalesInvoiceLine

from .models import CustomerRefund, CustomerReturnLine

ZERO_MONEY = Decimal("0.00")
ZERO_QUANTITY = Decimal("0.000")


class CustomerReturnHeaderForm(forms.Form):
    """Identifies the original completed sale a return is filed against.

    ``customer`` is not collected here: the return's customer must match the
    original sale exactly (``CustomerReturn.clean``), so the service derives
    it from ``sales_invoice`` instead of trusting separate input.
    """

    sales_invoice = forms.UUIDField()
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))


class CustomerReturnLineForm(forms.Form):
    """One returned line: the exact originally sold line/batch pair.

    Business-state rechecks (cumulative quantity/value caps against other
    posted returns) belong in ``apps.returns.services`` because they must
    run only after the return and its batches are locked at posting time;
    this form only validates the submitted values themselves.
    """

    sales_invoice_line = forms.ModelChoiceField(queryset=SalesInvoiceLine.objects.all())
    batch = forms.ModelChoiceField(queryset=MedicineBatch.objects.all())
    returned_quantity_base = forms.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal("0.001")
    )
    condition = forms.ChoiceField(choices=CustomerReturnLine.Condition.choices)
    restock = forms.BooleanField(required=False)
    refund_amount = forms.DecimalField(
        max_digits=14, decimal_places=2, min_value=ZERO_MONEY
    )

    def clean(self):
        cleaned_data = super().clean()
        sales_invoice_line = cleaned_data.get("sales_invoice_line")
        batch = cleaned_data.get("batch")
        condition = cleaned_data.get("condition")
        restock = cleaned_data.get("restock")

        if sales_invoice_line and batch:
            if not sales_invoice_line.batch_allocations.filter(batch_id=batch.pk).exists():
                self.add_error(
                    "batch", "The batch must have been allocated to the original sales line."
                )
        if restock and condition != CustomerReturnLine.Condition.RESELLABLE:
            self.add_error("restock", "Only resellable items may be restocked.")
        return cleaned_data


CustomerReturnLineFormSet = forms.formset_factory(
    CustomerReturnLineForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class CustomerRefundForm(forms.ModelForm):
    """Validates a refund before ``services.process_customer_refund``.

    The eligible-remaining-amount check runs in the service after the
    ``CustomerReturn`` row is locked, so this form only validates the
    submitted values themselves.
    """

    class Meta:
        model = CustomerRefund
        fields = ("payment_method", "amount", "reference", "refunded_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_method"].queryset = PaymentMethod.objects.filter(
            is_active=True
        ).order_by("name", "id")
        if not self.is_bound and not self.initial.get("refunded_at"):
            self.initial["refunded_at"] = timezone.now()

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None or amount <= ZERO_MONEY:
            raise forms.ValidationError("The refund amount must be greater than zero.")
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
