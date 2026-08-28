from django.contrib import admin

from .models import SaleBatchAllocation, SalesInvoice, SalesInvoiceLine


admin.site.register([SalesInvoice, SalesInvoiceLine, SaleBatchAllocation])
