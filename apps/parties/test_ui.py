from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import Customer, Prescriber, Supplier


class PartyWorkspaceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="parties-ui")
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="parties"))
        self.client.force_login(self.user)

    def test_existing_party_crud_search_and_status_flows(self):
        for route, model in (("supplier", Supplier), ("customer", Customer), ("prescriber", Prescriber)):
            with self.subTest(party=route):
                list_url = reverse(f"parties:{route}-list")
                create_url = reverse(f"parties:{route}-create")
                self.assertContains(self.client.get(list_url), f"No {route}s found")
                self.assertEqual(self.client.get(create_url).status_code, 200)
                response = self.client.post(create_url, {"code": "UI-1", "name": "Example party", "phone": "555-0100"})
                self.assertEqual(response.status_code, 302)
                record = model.objects.get(name="Example party")
                edit_url = reverse(f"parties:{route}-update", args=[record.pk])
                self.assertEqual(self.client.get(edit_url).status_code, 200)
                response = self.client.post(edit_url, {"code": "UI-1", "name": "Updated party", "phone": "555-0100"})
                self.assertEqual(response.status_code, 302)
                response = self.client.get(list_url, {"q": "555-0100", "status": "all"})
                self.assertContains(response, "Updated party")
                self.assertContains(response, 'value="all" selected')
                self.assertEqual(response.context["breadcrumbs"], [{"label": "Management"}, {"label": route.capitalize() + "s"}])
                self.assertEqual(self.client.post(reverse(f"parties:{route}-toggle-active", args=[record.pk])).status_code, 302)
                response = self.client.get(list_url, {"q": "Updated", "status": "inactive"})
                self.assertEqual(list(response.context[route + "s"]), [record])

    def test_read_only_lists_hide_actions_and_views_still_deny_writes(self):
        self.user.user_permissions.set(Permission.objects.filter(
            content_type__app_label="parties", codename__startswith="view_",
        ))
        for route, model in (("supplier", Supplier), ("customer", Customer), ("prescriber", Prescriber)):
            record = model.objects.create(**({"code": "READ"} if route != "prescriber" else {}), name="Read only")
            response = self.client.get(reverse(f"parties:{route}-list"))
            self.assertNotContains(response, f"Add {route}")
            self.assertNotContains(response, "Deactivate")
            self.assertNotContains(response, reverse(f"parties:{route}-update", args=[record.pk]))
            self.assertEqual(self.client.post(reverse(f"parties:{route}-toggle-active", args=[record.pk])).status_code, 403)

    def test_validation_retains_entered_contact_details(self):
        response = self.client.post(reverse("parties:supplier-create"), {
            "code": "", "name": "Keep supplier", "email": "invalid-email", "notes": "Keep these notes",
        })
        self.assertContains(response, 'value="Keep supplier"')
        self.assertContains(response, "Keep these notes")
        self.assertContains(response, 'id="id_email-error"')
        self.assertFalse(Supplier.objects.exists())
