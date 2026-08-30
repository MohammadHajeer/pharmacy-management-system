from decimal import Decimal

from django import forms

from .models import Category, Manufacturer, Medicine, MedicineBarcode, MedicineUnit


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        queryset = Category.objects.filter(name__iexact=name)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("A category with this name already exists.")
        return name


class ManufacturerForm(forms.ModelForm):
    class Meta:
        model = Manufacturer
        fields = ["name"]


class MedicineForm(forms.ModelForm):
    base_unit_name = forms.CharField(
        max_length=80,
        help_text="Required when creating a medicine. Its conversion factor is 1.",
    )

    class Meta:
        model = Medicine
        fields = [
            "name",
            "generic_name",
            "category",
            "manufacturer",
            "strength",
            "dosage_form",
            "prescription_required",
            "low_stock_threshold_base",
            "default_selling_price",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        self.fields["manufacturer"].queryset = Manufacturer.objects.filter(is_active=True)
        if not self.instance._state.adding:
            self.fields.pop("base_unit_name")

    def clean_default_selling_price(self):
        price = self.cleaned_data["default_selling_price"]
        if price is not None and price < Decimal("0"):
            raise forms.ValidationError("The selling price cannot be negative.")
        return price

    def clean_low_stock_threshold_base(self):
        threshold = self.cleaned_data.get("low_stock_threshold_base")
        if threshold is not None and threshold < Decimal("0"):
            raise forms.ValidationError("The low-stock threshold cannot be negative.")
        return threshold


class MedicineUnitForm(forms.ModelForm):
    class Meta:
        model = MedicineUnit
        fields = [
            "name",
            "conversion_to_base",
            "is_base_unit",
            "purchase_allowed",
            "sale_allowed",
        ]

    def __init__(self, *args, medicine=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.medicine = medicine or (self.instance.medicine if self.instance.pk else None)

    def clean(self):
        cleaned_data = super().clean()
        is_base_unit = cleaned_data.get("is_base_unit")
        conversion_to_base = cleaned_data.get("conversion_to_base")

        if is_base_unit and conversion_to_base is not None and conversion_to_base != Decimal("1"):
            self.add_error(
                "conversion_to_base", "A base unit must have a conversion factor of 1."
            )

        if conversion_to_base is not None and conversion_to_base <= 0:
            self.add_error("conversion_to_base", "The conversion factor must be greater than zero.")

        if is_base_unit and self.medicine is not None:
            existing_base_units = MedicineUnit.objects.filter(
                medicine=self.medicine,
                is_base_unit=True,
                is_active=True,
            )
            if self.instance.pk:
                existing_base_units = existing_base_units.exclude(pk=self.instance.pk)
            if existing_base_units.exists():
                self.add_error(
                    "is_base_unit",
                    "This medicine already has an active base unit.",
                )

        if (
            self.instance.pk
            and self.instance.is_active
            and self.instance.is_base_unit
            and not is_base_unit
        ):
            self.add_error(
                "is_base_unit",
                "The active base unit cannot be converted to a non-base unit.",
            )

        name = cleaned_data.get("name")
        if name and self.medicine is not None:
            duplicate = MedicineUnit.objects.filter(medicine=self.medicine, name__iexact=name)
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                self.add_error("name", "This medicine already has a unit with this name.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.medicine is not None:
            instance.medicine = self.medicine
        if commit:
            instance.full_clean()
            instance.save()
        return instance


class MedicineBarcodeForm(forms.ModelForm):
    class Meta:
        model = MedicineBarcode
        fields = ["medicine_unit", "barcode"]

    def __init__(self, *args, medicine=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.medicine = medicine or (
            self.instance.medicine_unit.medicine if self.instance.pk else None
        )
        if self.medicine is not None:
            self.fields["medicine_unit"].queryset = MedicineUnit.objects.filter(
                medicine=self.medicine, is_active=True
            )

    def clean_barcode(self):
        barcode = self.cleaned_data["barcode"].strip()
        queryset = MedicineBarcode.objects.filter(barcode=barcode)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("This barcode is already registered.")
        return barcode
