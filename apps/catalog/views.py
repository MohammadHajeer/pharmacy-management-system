from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.shortcuts import render

from .models import Medicine


@login_required
@permission_required("catalog.view_medicine", raise_exception=True)
def medicine_list(request):
    medicines = Medicine.objects.all()

    return render(
        request,
        "catalog/medicines/list.html",
        {
            "page_context": "Medicines",
            "breadcrumbs": [
                {"label": "Catalog"},
                {"label": "Medicines"},
            ],
            "medicines": medicines,
        },
    )
