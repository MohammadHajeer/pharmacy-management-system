import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

ROLES = {
    "owner": "Owner / Admin",
    "pharmacist": "Pharmacist",
    "inventory": "Inventory Manager",
    "accountant": "Accountant",
}


class Command(BaseCommand):
    help = "Create development roles and users."

    def handle(self, *args, **options):
        password = os.getenv("DEV_AUTH_PASSWORD")

        if not password:
            raise CommandError("DEV_AUTH_PASSWORD is missing from the environment.")

        User = get_user_model()

        for username, group_name in ROLES.items():
            group, _ = Group.objects.get_or_create(name=group_name)

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
