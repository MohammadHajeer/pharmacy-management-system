from django import forms

from .models import PaymentMethod, PharmacySettings, TaxRate


class PharmacySettingsForm(forms.ModelForm):
    class Meta:
        model = PharmacySettings
        fields = (
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
        )

    def clean_currency_code(self):
        currency_code = self.cleaned_data["currency_code"].strip().upper()
        if (
            len(currency_code) != 3
            or not currency_code.isascii()
            or not currency_code.isalpha()
        ):
            raise forms.ValidationError(
                "Enter a three-letter ASCII currency code, such as USD."
            )
        return currency_code


class TaxRateForm(forms.ModelForm):
    class Meta:
        model = TaxRate
        fields = ("code", "name", "rate_percent", "is_active")

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()


class PaymentMethodForm(forms.ModelForm):
    class Meta:
        model = PaymentMethod
        fields = ("code", "name", "requires_reference", "is_active")

    def clean_code(self):
        return self.cleaned_data["code"].strip().upper()
