from django import forms
from django.forms import BaseFormSet, formset_factory

from apps.catalog.models import Medicine, MedicineUnit
from apps.parties.models import Customer
from apps.prescriptions.models import Prescription


AUTHORITATIVE_INVOICE_FIELDS = frozenset(
    {
        "invoice_number",
        "currency_code",
        "subtotal",
        "discount_total",
        "tax_total",
        "grand_total",
        "paid_total",
        "balance_due",
        "payment_status",
        "pharmacist",
        "pharmacy_name_snapshot",
        "customer_name_snapshot",
        "customer_phone_snapshot",
    }
)

AUTHORITATIVE_LINE_FIELDS = frozenset(
    {
        "conversion_to_base_snapshot",
        "requested_quantity_base",
        "unit_price",
        "line_subtotal",
        "tax_rate_percent",
        "tax_amount",
        "line_total",
        "medicine_description_snapshot",
        "unit_name_snapshot",
        "prescription_required_snapshot",
    }
)


class PosMedicineSearchForm(forms.Form):
    q = forms.CharField(required=False, max_length=200)
    limit = forms.IntegerField(required=False, min_value=1, max_value=100, initial=20)


class PosBarcodeLookupForm(forms.Form):
    barcode = forms.CharField(max_length=64)

    def clean_barcode(self):
        barcode = self.cleaned_data["barcode"].strip()
        if not barcode:
            raise forms.ValidationError("Enter a barcode.")
        return barcode


class DraftSaleForm(forms.Form):
    customer = forms.ModelChoiceField(queryset=Customer.objects.none(), required=False)
    prescription = forms.ModelChoiceField(
        queryset=Prescription.objects.none(),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.filter(is_active=True).order_by(
            "name",
            "code",
        )
        self.fields["prescription"].queryset = Prescription.objects.order_by(
            "-prescription_date",
            "-created_at",
        )

    def clean(self):
        cleaned_data = super().clean()
        supplied = [
            field_name
            for field_name in AUTHORITATIVE_INVOICE_FIELDS
            if self.data.get(self.add_prefix(field_name)) not in (None, "")
        ]
        if supplied:
            raise forms.ValidationError(
                "Invoice numbers, snapshots, payment state, and totals are calculated "
                "by the server and must not be submitted."
            )
        return cleaned_data


class DraftSaleLineForm(forms.Form):
    medicine = forms.ModelChoiceField(queryset=Medicine.objects.none())
    medicine_unit = forms.ModelChoiceField(queryset=MedicineUnit.objects.none())
    quantity = forms.DecimalField(max_digits=14, decimal_places=3, min_value=0)
    discount_amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=0,
        required=False,
        initial=0,
    )
    prescription_warning_acknowledged = forms.BooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["medicine"].queryset = Medicine.objects.filter(is_active=True).order_by(
            "name"
        )
        self.fields["medicine_unit"].queryset = MedicineUnit.objects.filter(
            is_active=True,
            sale_allowed=True,
            medicine__is_active=True,
        ).select_related("medicine").order_by("medicine__name", "name")

    def clean(self):
        cleaned_data = super().clean()
        supplied = [
            field_name
            for field_name in AUTHORITATIVE_LINE_FIELDS
            if self.data.get(self.add_prefix(field_name)) not in (None, "")
        ]
        if supplied:
            raise forms.ValidationError(
                "Conversion, price, tax, snapshots, and totals are calculated by the "
                "server and must not be submitted."
            )

        medicine = cleaned_data.get("medicine")
        medicine_unit = cleaned_data.get("medicine_unit")
        if medicine and medicine_unit and medicine_unit.medicine_id != medicine.id:
            self.add_error(
                "medicine_unit",
                "The selected unit must belong to the selected medicine.",
            )

        quantity = cleaned_data.get("quantity")
        if quantity is not None and quantity <= 0:
            self.add_error("quantity", "Quantity must be greater than zero.")
        return cleaned_data


class BaseDraftSaleLineFormSet(BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        if not self.forms:
            raise forms.ValidationError("At least one sale line is required.")


DraftSaleLineFormSet = formset_factory(
    DraftSaleLineForm,
    formset=BaseDraftSaleLineFormSet,
    extra=0,
    min_num=1,
    validate_min=True,
)
