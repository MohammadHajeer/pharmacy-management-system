from decimal import Decimal

from django import forms

from apps.catalog.models import Medicine, MedicineUnit
from apps.parties.models import Supplier


class PurchaseInvoiceHeaderForm(forms.Form):
    supplier = forms.ModelChoiceField(queryset=Supplier.objects.filter(is_active=True))
    supplier_invoice_reference = forms.CharField(max_length=100, required=False)
    invoice_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    due_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    currency_code = forms.CharField(max_length=3)


class PurchaseInvoiceLineForm(forms.Form):
    medicine = forms.ModelChoiceField(queryset=Medicine.objects.filter(is_active=True))
    medicine_unit = forms.ModelChoiceField(
        queryset=MedicineUnit.objects.filter(is_active=True, purchase_allowed=True)
    )
    quantity = forms.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))
    unit_cost = forms.DecimalField(max_digits=14, decimal_places=4, min_value=Decimal("0"))
    discount_amount = forms.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0"), required=False
    )
    tax_rate_percent = forms.DecimalField(
        max_digits=7,
        decimal_places=4,
        min_value=Decimal("0"),
        max_value=Decimal("100"),
        required=False,
    )
    batch_number = forms.CharField(max_length=100)
    expiry_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))

    def clean(self):
        cleaned_data = super().clean()
        medicine = cleaned_data.get("medicine")
        medicine_unit = cleaned_data.get("medicine_unit")
        if medicine and medicine_unit and medicine_unit.medicine_id != medicine.pk:
            self.add_error("medicine_unit", "The unit must belong to the selected medicine.")
        return cleaned_data


PurchaseInvoiceLineFormSet = forms.formset_factory(
    PurchaseInvoiceLineForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)
