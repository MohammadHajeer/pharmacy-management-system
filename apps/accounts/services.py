from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .permissions import (
    APPROVED_PERMISSION_NAMES,
    BUSINESS_ROLES,
    OPERATIONAL_ROLES,
    OPERATIONAL_PERMISSION_NAMES,
    OWNER_ROLE,
)


User = get_user_model()


def is_owner_admin(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and user.is_active
        and user.groups.filter(name=OWNER_ROLE).exists()
    )


def require_owner_admin(actor, permission):
    if not is_owner_admin(actor) or not actor.has_perm(permission):
        raise PermissionDenied


def business_role_for(user):
    return user.groups.filter(name__in=BUSINESS_ROLES).order_by("name").first()


def _locked_staff_user(user_id):
    user = User.objects.select_for_update().get(pk=user_id)
    if not user.groups.filter(name__in=BUSINESS_ROLES).exists():
        raise PermissionDenied
    return user


def _locked_business_group(role):
    if role not in BUSINESS_ROLES:
        raise ValidationError("Select a valid PHARMANEX business role.")
    group, _ = Group.objects.get_or_create(name=role)
    return Group.objects.select_for_update().get(pk=group.pk)


def _assert_owner_will_remain(target):
    if not target.is_active or not target.groups.filter(name=OWNER_ROLE).exists():
        return
    active_owner_ids = list(
        User.objects.select_for_update()
        .filter(is_active=True, groups__name=OWNER_ROLE)
        .distinct()
        .values_list("pk", flat=True)
    )
    if active_owner_ids == [target.pk]:
        raise ValidationError(
            "The last active Owner / Admin account must keep administrative access."
        )


def create_staff_user(*, actor, form):
    require_owner_admin(actor, "auth.add_user")
    if not form.is_valid():
        return None
    with transaction.atomic():
        role = _locked_business_group(form.cleaned_data["role"])
        user = form.save(commit=False)
        user.is_staff = False
        user.is_superuser = False
        user.set_password(form.cleaned_data["password1"])
        user.save()
        user.groups.add(role)
    return user


def update_staff_profile(*, actor, user_id, form):
    require_owner_admin(actor, "auth.change_user")
    if not form.is_valid():
        return None
    with transaction.atomic():
        target = _locked_staff_user(user_id)
        for field in ("username", "first_name", "last_name", "email"):
            setattr(target, field, form.cleaned_data[field])
        target.full_clean(exclude=["password"])
        target.save(update_fields=["username", "first_name", "last_name", "email"])
    return target


def assign_staff_role(*, actor, user_id, role):
    require_owner_admin(actor, "auth.change_user")
    with transaction.atomic():
        target = _locked_staff_user(user_id)
        selected_group = _locked_business_group(role)
        if role != OWNER_ROLE:
            _assert_owner_will_remain(target)
        business_groups = Group.objects.filter(name__in=BUSINESS_ROLES)
        target.groups.remove(*business_groups)
        target.groups.add(selected_group)
    return target


def set_staff_active(*, actor, user_id, is_active):
    require_owner_admin(actor, "auth.change_user")
    with transaction.atomic():
        target = _locked_staff_user(user_id)
        if not is_active:
            if target.pk == actor.pk:
                raise ValidationError("You cannot deactivate your own signed-in account.")
            _assert_owner_will_remain(target)
        target.is_active = is_active
        target.save(update_fields=["is_active"])
    return target


def reset_staff_password(*, actor, user_id, password):
    require_owner_admin(actor, "auth.change_user")
    with transaction.atomic():
        target = _locked_staff_user(user_id)
        target.set_password(password)
        target.save(update_fields=["password"])
    return target


def permission_objects(permission_names=APPROVED_PERMISSION_NAMES):
    requested = set(permission_names)
    query = Permission.objects.select_related("content_type").filter(
        content_type__app_label__in={name.split(".", 1)[0] for name in requested}
    )
    return {
        f"{permission.content_type.app_label}.{permission.codename}": permission
        for permission in query
        if f"{permission.content_type.app_label}.{permission.codename}" in requested
    }


def update_role_permissions(*, actor, group_name, permission_names):
    require_owner_admin(actor, "auth.change_group")
    supplied = set(permission_names)
    if group_name not in OPERATIONAL_ROLES:
        raise ValidationError("Only operational PHARMANEX roles can be changed.")
    if not supplied <= OPERATIONAL_PERMISSION_NAMES:
        raise ValidationError("The submission contains an unapproved permission.")

    with transaction.atomic():
        group = _locked_business_group(group_name)
        approved = permission_objects()
        missing = supplied - approved.keys()
        if missing:
            raise ValidationError("The submission contains an unavailable permission.")
        current_approved = [
            permission
            for name, permission in approved.items()
            if name in APPROVED_PERMISSION_NAMES
        ]
        group.permissions.remove(*current_approved)
        group.permissions.add(*(approved[name] for name in supplied))

        owner = _locked_business_group(OWNER_ROLE)
        owner.permissions.add(*approved.values())
    return group
