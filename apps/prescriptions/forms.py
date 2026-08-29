from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from .models import Prescription, PrescriptionItem


class PrescriptionForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = (
            "reference_number",
            "customer",
            "prescriber",
            "prescription_date",
            "notes",
        )


class PrescriptionItemForm(forms.ModelForm):
    class Meta:
        model = PrescriptionItem
        fields = (
            "medicine",
            "quantity_prescribed",
            "dosage_instructions",
            "notes",
        )

    def clean_quantity_prescribed(self):
        quantity = self.cleaned_data.get("quantity_prescribed")
        if quantity is not None and quantity <= 0:
            raise forms.ValidationError(
                "Quantity prescribed must be greater than zero."
            )
        return quantity


class BasePrescriptionItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        has_item = any(
            form.cleaned_data.get("medicine")
            and not form.cleaned_data.get("DELETE", False)
            for form in self.forms
            if form.cleaned_data
        )
        if not has_item:
            raise forms.ValidationError(
                "At least one prescription medicine item is required."
            )


PrescriptionItemFormSet = inlineformset_factory(
    Prescription,
    PrescriptionItem,
    form=PrescriptionItemForm,
    formset=BasePrescriptionItemFormSet,
    fields=(
        "medicine",
        "quantity_prescribed",
        "dosage_instructions",
        "notes",
    ),
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)
