from django.contrib import admin

from .models import Customer, Prescriber, Supplier


admin.site.register([Supplier, Customer, Prescriber])
