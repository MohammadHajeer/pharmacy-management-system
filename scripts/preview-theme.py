"""Disposable cross-workspace theme review: uv run python scripts/preview-theme.py.

Only synthetic fixtures in an in-memory SQLite test database; never uses Neon.
Stop the process to discard the preview, including its random local login.
"""
import os
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

import django

django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.db import connection
from django.test import Client
from django.test.utils import setup_databases
from django.urls import reverse
from django.utils import timezone

from apps.finance.services import post_customer_payment, post_supplier_payment
from apps.accounts.permissions import BUSINESS_ROLES, OWNER_ROLE
from apps.finance.tests import _FinanceFixtureMixin
from apps.parties.models import Prescriber
from apps.purchasing.models import PurchaseInvoice
from apps.sales.tests import PosDraftServiceTests

settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]


class PreviewAutoLoginMiddleware:
    """Authenticate the disposable preview actor without transmitting credentials."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        requested_role = request.GET.get("preview_as")
        preview_user_id = settings.PREVIEW_ROLE_USER_IDS.get(
            requested_role, settings.PREVIEW_USER_ID
        )
        if not request.user.is_authenticated or (
            requested_role and request.user.pk != preview_user_id
        ):
            from django.contrib.auth import get_user_model, login

            user = get_user_model().objects.get(pk=preview_user_id)
            user.backend = "django.contrib.auth.backends.ModelBackend"
            login(request, user)
        return self.get_response(request)


settings.MIDDLEWARE.append("__main__.PreviewAutoLoginMiddleware")
settings.TEMPLATES[0]["APP_DIRS"] = False
settings.TEMPLATES[0]["OPTIONS"]["loaders"] = [
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]
setup_databases(verbosity=0, interactive=False)
assert connection.vendor == "sqlite" and "memory" in str(connection.settings_dict["NAME"])
PosDraftServiceTests.setUpTestData()
_FinanceFixtureMixin._build_fixtures()
pos = PosDraftServiceTests
finance = _FinanceFixtureMixin
actor = pos.authorized_user
actor.user_permissions.set(Permission.objects.all())
preview_groups = {
    name: Group.objects.get_or_create(name=name)[0] for name in BUSINESS_ROLES
}
preview_groups[OWNER_ROLE].permissions.set(Permission.objects.all())
actor.groups.add(preview_groups[OWNER_ROLE])
password = secrets.token_urlsafe(18)
actor.set_password(password)
actor.save()
settings.PREVIEW_USER_ID = actor.pk
preview_role_users = {"owner": actor.pk}
for role_name in BUSINESS_ROLES:
    if role_name == OWNER_ROLE:
        continue
    role_user = get_user_model().objects.create_user(
        username=f"preview-{role_name.lower().replace(' ', '-')}",
    )
    role_user.groups.add(preview_groups[role_name])
    preview_role_users[role_name.lower().replace(" ", "-")] = role_user.pk
settings.PREVIEW_ROLE_USER_IDS = preview_role_users
Prescriber.objects.create(name="Preview prescriber")
pos.pharmacy_settings.pharmacy_name = "Local theme review pharmacy"
pos.pharmacy_settings.save()
finance.sales_invoice.pharmacy_name_snapshot = pos.pharmacy_settings.pharmacy_name
finance.sales_invoice.customer_name_snapshot = finance.customer.name
finance.sales_invoice.save()
for service, invoice, field in (
    (post_customer_payment, finance.sales_invoice, "sales_invoice"),
    (post_supplier_payment, finance.purchase_invoice, "purchase_invoice"),
):
    form, payment = service(actor=actor, **{field: invoice}, data={
        "amount": "20.00", "payment_method": str(finance.payment_method.pk),
        "paid_at": timezone.now(), "reference": "PREVIEW-ONLY",
    })
    assert not form.errors, form.errors
PurchaseInvoice.objects.create(
    invoice_number="PREVIEW-PREVIOUS", supplier=finance.supplier,
    supplier_name_snapshot=finance.supplier.name, created_by=actor,
    status=PurchaseInvoice.Status.POSTED, currency_code="USD",
    invoice_date=timezone.localdate() - timezone.timedelta(days=40),
    posted_at=timezone.now() - timezone.timedelta(days=40),
)
client = Client()
client.force_login(actor)
response = client.post(reverse("sales:pos"), pos().draft_data(
    customer=str(pos.customer.pk), **{"lines-0-prescription_warning_acknowledged": "on"},
))
assert response.status_code == 302, response.status_code
print("Synthetic in-memory SQLite preview: http://127.0.0.1:8017/", flush=True)
print(f"Temporary login: {actor.username} / {password}", flush=True)
call_command("runserver", "127.0.0.1:8017", use_reloader=False)
