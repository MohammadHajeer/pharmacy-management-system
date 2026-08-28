from django.contrib import admin

from .models import (
    CustomerRefund,
    CustomerReturn,
    CustomerReturnLine,
    SupplierReturn,
    SupplierReturnLine,
)


admin.site.register(
    [
        CustomerReturn,
        CustomerReturnLine,
        CustomerRefund,
        SupplierReturn,
        SupplierReturnLine,
    ]
)
