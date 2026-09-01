from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .permissions import BUSINESS_ROLES, OWNER_ROLE


User = get_user_model()


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AdministrationTestBase(TestCase):
    owner_permissions = (
        "auth.view_user",
        "auth.add_user",
        "auth.change_user",
        "auth.view_group",
        "auth.change_group",
    )

    @classmethod
    def setUpTestData(cls):
        cls.groups = {name: Group.objects.create(name=name) for name in BUSINESS_ROLES}
        permissions = []
        for permission_name in cls.owner_permissions:
            app_label, codename = permission_name.split(".", 1)
            permissions.append(
                Permission.objects.get(
                    content_type__app_label=app_label,
                    codename=codename,
                )
            )
        cls.groups[OWNER_ROLE].permissions.add(*permissions)
        cls.owner = User.objects.create_user(
            username="owner",
            password="Owner-Test-Password-482!",
        )
        cls.owner.groups.add(cls.groups[OWNER_ROLE])
        cls.pharmacist = User.objects.create_user(
            username="pharmacist",
            first_name="Nora",
            email="nora@example.com",
            password="Pharmacist-Test-482!",
        )
        cls.pharmacist.groups.add(cls.groups["Pharmacist"])

    def setUp(self):
        self.client.force_login(self.owner)


class StaffAccountAccessTests(AdministrationTestBase):
    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        url = reverse("accounts:staff-list")
        response = self.client.get(url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}")

    def test_non_owner_is_denied_even_with_auth_permissions(self):
        self.pharmacist.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="auth",
                codename__in=["view_user", "add_user", "change_user", "view_group", "change_group"],
            )
        )
        self.client.force_login(self.pharmacist)
        self.assertEqual(self.client.get(reverse("accounts:staff-list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("accounts:role-permissions")).status_code, 403)

    def test_owner_can_open_registry_and_navigation_is_route_specific(self):
        response = self.client.get(reverse("accounts:staff-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff registry")
        active = [item["label"] for item in response.context["dashboard_navigation"] if item["is_active"]]
        self.assertEqual(active, ["Staff Accounts"])


class StaffAccountWorkflowTests(AdministrationTestBase):
    def test_create_staff_account_validates_password_and_safe_flags(self):
        url = reverse("accounts:staff-create")
        weak = self.client.post(url, {
            "username": "weak-user", "role": "Accountant",
            "password1": "password", "password2": "password", "is_active": "on",
        })
        self.assertEqual(weak.status_code, 200)
        self.assertContains(weak, "This password is too common")
        self.assertNotContains(weak, 'value="password"')
        self.assertFalse(User.objects.filter(username="weak-user").exists())

        response = self.client.post(url, {
            "username": "new-accountant", "first_name": "Mira", "last_name": "Haddad",
            "email": "mira@example.com", "role": "Accountant",
            "password1": "Mira-Pharmacy-482!", "password2": "Mira-Pharmacy-482!",
            "is_active": "on",
        })
        created = User.objects.get(username="new-accountant")
        self.assertRedirects(response, reverse("accounts:staff-detail", args=[created.pk]))
        self.assertTrue(created.check_password("Mira-Pharmacy-482!"))
        self.assertFalse(created.is_staff)
        self.assertFalse(created.is_superuser)
        self.assertEqual(list(created.groups.values_list("name", flat=True)), ["Accountant"])

    def test_role_reassignment_preserves_unrelated_group(self):
        internal = Group.objects.create(name="Internal automation")
        self.pharmacist.groups.add(internal)
        response = self.client.post(
            reverse("accounts:staff-role-update", args=[self.pharmacist.pk]),
            {"role": "Inventory Manager"},
        )
        self.assertRedirects(response, reverse("accounts:staff-detail", args=[self.pharmacist.pk]))
        self.assertEqual(
            set(self.pharmacist.groups.values_list("name", flat=True)),
            {"Inventory Manager", "Internal automation"},
        )

    def test_deactivate_reactivate_and_self_deactivation_guard(self):
        status_url = reverse("accounts:staff-status-update", args=[self.pharmacist.pk])
        self.client.post(status_url, {})
        self.pharmacist.refresh_from_db()
        self.assertFalse(self.pharmacist.is_active)
        self.client.post(status_url, {"is_active": "on"})
        self.pharmacist.refresh_from_db()
        self.assertTrue(self.pharmacist.is_active)

        self.client.post(reverse("accounts:staff-status-update", args=[self.owner.pk]), {})
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)

    def test_last_active_owner_cannot_be_deactivated_or_reassigned(self):
        self.client.post(reverse("accounts:staff-status-update", args=[self.owner.pk]), {})
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_active)
        response = self.client.post(
            reverse("accounts:staff-role-update", args=[self.owner.pk]),
            {"role": "Accountant"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(self.owner.groups.filter(name=OWNER_ROLE).exists())

    def test_password_reset_changes_credentials_without_exposing_them(self):
        old_password = "Pharmacist-Test-482!"
        new_password = "Replaced-Pharmacy-736!"
        response = self.client.post(
            reverse("accounts:staff-password-reset", args=[self.pharmacist.pk]),
            {"password1": new_password, "password2": new_password},
        )
        self.assertRedirects(response, reverse("accounts:staff-detail", args=[self.pharmacist.pk]))
        self.pharmacist.refresh_from_db()
        self.assertFalse(self.pharmacist.check_password(old_password))
        self.assertTrue(self.pharmacist.check_password(new_password))
        detail = self.client.get(reverse("accounts:staff-detail", args=[self.pharmacist.pk]))
        self.assertNotContains(detail, old_password)
        self.assertNotContains(detail, new_password)
        self.assertNotContains(detail, self.pharmacist.password)

        rejected_password = "Mismatch-Password-934!"
        rejected = self.client.post(
            reverse("accounts:staff-password-reset", args=[self.pharmacist.pk]),
            {"password1": rejected_password, "password2": "Different-934!"},
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertNotContains(rejected, rejected_password, status_code=400)

    def test_registry_search_role_status_and_pagination(self):
        for index in range(30):
            user = User.objects.create_user(username=f"temp-{index:02d}")
            user.groups.add(self.groups["Accountant"])
        page = self.client.get(reverse("accounts:staff-list"), {"role": "Accountant", "page": 2})
        self.assertEqual(page.context["page_obj"].number, 2)
        self.assertEqual(page.context["page_obj"].paginator.count, 30)
        search = self.client.get(reverse("accounts:staff-list"), {"q": "Nora", "status": "active"})
        self.assertEqual(search.context["page_obj"].paginator.count, 1)
        self.assertContains(search, "pharmacist")

    def test_mutations_are_post_only(self):
        for name in ("staff-update", "staff-role-update", "staff-status-update", "staff-password-reset"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(f"accounts:{name}", args=[self.pharmacist.pk])).status_code, 405)


class RolePermissionWorkflowTests(AdministrationTestBase):
    def test_owner_can_open_matrix_with_locked_owner_capabilities(self):
        response = self.client.get(reverse("accounts:role-permissions"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Owner / Admin retains required full system access")
        self.assertContains(response, "Locked")

    def test_allowed_update_changes_has_perm_and_preserves_owner_requirements(self):
        permission_name = "catalog.view_medicine"
        response = self.client.post(
            reverse("accounts:role-permissions-update"),
            {"role": "Pharmacist", "permissions": [permission_name]},
        )
        self.assertRedirects(
            response,
            f"{reverse('accounts:role-permissions')}?role=pharmacist",
        )
        self.pharmacist = User.objects.get(pk=self.pharmacist.pk)
        self.assertTrue(self.pharmacist.has_perm(permission_name))
        self.assertTrue(self.groups[OWNER_ROLE].permissions.filter(codename="view_user").exists())

    def test_permission_injection_and_malformed_submission_are_rejected(self):
        url = reverse("accounts:role-permissions-update")
        injected = self.client.post(
            url,
            {"role": "Pharmacist", "permissions": ["admin.delete_logentry"]},
        )
        self.assertEqual(injected.status_code, 400)
        self.assertFalse(self.groups["Pharmacist"].permissions.exists())
        malformed = self.client.post(url, {"role": "Unknown", "permissions": []})
        self.assertEqual(malformed.status_code, 400)

    def test_permission_update_requires_post_and_csrf(self):
        url = reverse("accounts:role-permissions-update")
        self.assertEqual(self.client.get(url).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        self.assertEqual(
            csrf_client.post(url, {"role": "Pharmacist", "permissions": []}).status_code,
            403,
        )
