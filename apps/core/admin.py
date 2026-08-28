from django.contrib import admin

from .models import PaymentMethod, PharmacySettings, TaxRate


admin.site.register([PharmacySettings, TaxRate, PaymentMethod])
