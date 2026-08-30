from django import forms

from .models import Customer, Prescriber, Supplier


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            "code",
            "name",
            "contact_person",
            "phone",
            "email",
            "address",
            "notes",
        ]

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        queryset = Supplier.objects.filter(code__iexact=code)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("A supplier with this code already exists.")
        return code


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "code",
            "name",
            "phone",
            "email",
            "address",
            "notes",
        ]

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        queryset = Customer.objects.filter(code__iexact=code)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise forms.ValidationError("A customer with this code already exists.")
        return code


class PrescriberForm(forms.ModelForm):
    class Meta:
        model = Prescriber
        fields = [
            "name",
            "phone",
            "professional_identifier",
            "notes",
        ]
