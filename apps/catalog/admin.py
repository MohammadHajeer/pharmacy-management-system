from django.contrib import admin

from .models import Category, Manufacturer, Medicine, MedicineBarcode, MedicineUnit


admin.site.register([Category, Manufacturer, Medicine, MedicineUnit, MedicineBarcode])
