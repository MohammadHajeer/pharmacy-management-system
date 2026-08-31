"""Disposable local POS review server. Never connects to the configured database.

Run: uv run python scripts/preview-sales.py
Uses Django's isolated SQLite test database and synthetic test fixtures. Data
disappears when the process exits; no demo seeder or production settings writes.
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

from django.contrib.auth.models import Permission
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test.utils import setup_databases
from django.utils import timezone

from apps.core.models import PaymentMethod
from apps.inventory.models import MedicineBatch
from apps.sales.models import SalesInvoice
from apps.sales.tests import PosDraftServiceTests

# Show template edits on reload without restarting (and losing) the fixture DB.
settings.TEMPLATES[0]["APP_DIRS"] = False
settings.TEMPLATES[0]["OPTIONS"]["loaders"] = [
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]

setup_databases(verbosity=0, interactive=False)
assert connection.vendor == "sqlite" and "memory" in str(connection.settings_dict["NAME"])
PosDraftServiceTests.setUpTestData()
fixture = PosDraftServiceTests
actor = fixture.authorized_user
actor.user_permissions.set(Permission.objects.filter(content_type__app_label__in=("sales", "finance")))
password = secrets.token_urlsafe(18)
actor.set_password(password)
actor.save()
PaymentMethod.objects.create(code="PREVIEW-CASH", name="Cash")
PaymentMethod.objects.create(code="PREVIEW-CARD", name="Card", requires_reference=True)
MedicineBatch.objects.create(
    medicine=fixture.other_medicine, batch_number="PREVIEW-GENERAL",
    expiry_date=timezone.localdate() + timezone.timedelta(days=180),
    acquisition_cost_per_base_unit="1.0000", quantity_available_base="50.000",
    first_received_at=timezone.now(),
)
SalesInvoice.objects.bulk_create([
    SalesInvoice(pharmacist=actor, customer=fixture.customer, currency_code="USD")
    for _ in range(28)
])
fixture.pharmacy_settings.invoice_header = "Local verification pharmacy · Synthetic data"
fixture.pharmacy_settings.invoice_footer = "Thank you · Invoice copy"
fixture.pharmacy_settings.receipt_footer = "Thank you · Receipt copy"
fixture.pharmacy_settings.save()
print("Isolated in-memory SQLite only. Open http://127.0.0.1:8017/sales/pos/", flush=True)
print(f"Temporary login: {actor.username} / {password}", flush=True)
call_command("runserver", "127.0.0.1:8017", use_reloader=False)
