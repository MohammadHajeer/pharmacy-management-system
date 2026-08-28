from django.contrib import admin

from .models import Prescription, PrescriptionItem


admin.site.register([Prescription, PrescriptionItem])
