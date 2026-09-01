import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.permissions import APPROVED_PERMISSION_NAMES

ROLES = {
    "owner": "Owner / Admin",
    "pharmacist": "Pharmacist",
    "inventory": "Inventory Manager",
    "accountant": "Accountant",
}

FINANCIAL_REPORT_ROLES = {"Owner / Admin", "Accountant"}


class Command(BaseCommand):
    help = "Create development roles and users."

    def handle(self, *args, **options):
        password = os.getenv("DEV_AUTH_PASSWORD")

        if not password:
            raise CommandError("DEV_AUTH_PASSWORD is missing from the environment.")

        User = get_user_model()

        try:
            financial_report_permission = Permission.objects.get(
                content_type__app_label="finance",
                content_type__model="customerpayment",
                codename="view_financial_reports",
            )
        except Permission.DoesNotExist as error:
            raise CommandError(
                "finance.view_financial_reports is unavailable. Apply the current migrations first."
            ) from error

        for username, group_name in ROLES.items():
            group, _ = Group.objects.get_or_create(name=group_name)

            if group_name == "Owner / Admin":
                owner_permissions = []
                for permission_name in APPROVED_PERMISSION_NAMES:
                    app_label, codename = permission_name.split(".", 1)
                    permission = Permission.objects.filter(
                        content_type__app_label=app_label,
                        codename=codename,
                    ).first()
                    if permission is not None:
                        owner_permissions.append(permission)
                group.permissions.add(*owner_permissions)
            elif group_name in FINANCIAL_REPORT_ROLES:
                group.permissions.add(financial_report_permission)
            else:
                group.permissions.remove(financial_report_permission)

            user, created = User.objects.get_or_create(
                username=username,
            )

            if created:
                user.set_password(password)
                user.save()

            user.groups.add(group)

            action = "Created" if created else "Found"

            self.stdout.write(self.style.SUCCESS(f"{action} {username} → {group_name}"))

        self.stdout.write(self.style.SUCCESS("Development auth setup complete."))
