from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import redirect, render
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.pagination import pagination_context

from .forms import (
    AdminPasswordResetForm,
    RolePermissionForm,
    StaffCreateForm,
    StaffRoleForm,
    StaffStatusForm,
    StaffUpdateForm,
)
from .permissions import (
    APPROVED_PERMISSION_NAMES,
    BUSINESS_ROLES,
    OPERATIONAL_ROLES,
    OPERATIONAL_PERMISSION_NAMES,
    OWNER_ROLE,
    PERMISSION_GROUPS,
    ROLE_SLUGS,
    ROLE_TO_SLUG,
)
from .services import (
    assign_staff_role,
    create_staff_user,
    is_owner_admin,
    permission_objects,
    reset_staff_password,
    set_staff_active,
    update_role_permissions,
    update_staff_profile,
)


User = get_user_model()


def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    form = AuthenticationForm(request, data=request.POST or None)

    if request.method == "POST":
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            return redirect("dashboard:home")

        if form.non_field_errors():
            messages.error(
                request,
                "Please check your username and password and try again.",
            )

    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
            "toast_title": "Unable to sign in" if form.non_field_errors() else "",
            "toast_duration": 6000 if form.non_field_errors() else None,
        },
    )


@require_POST
def logout_view(request):
    logout(request)
    return redirect("accounts:login")


def _require_owner_permission(request, permission):
    if not is_owner_admin(request.user) or not request.user.has_perm(permission):
        raise PermissionDenied


def _staff_queryset():
    return (
        User.objects.filter(groups__name__in=BUSINESS_ROLES)
        .prefetch_related("groups")
        .distinct()
    )


def _staff_user(pk):
    return get_object_or_404(_staff_queryset(), pk=pk)


def _role_name(user):
    roles = {group.name for group in user.groups.all()}
    return next((role for role in BUSINESS_ROLES if role in roles), "Unassigned")


@login_required
@require_GET
def staff_list(request):
    _require_owner_permission(request, "auth.view_user")
    staff = _staff_queryset().order_by("username", "pk")
    query = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    status = request.GET.get("status", "")

    if query:
        staff = staff.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    if role:
        if role in BUSINESS_ROLES:
            staff = staff.filter(groups__name=role)
        else:
            staff = staff.none()
    if status:
        if status == "active":
            staff = staff.filter(is_active=True)
        elif status == "inactive":
            staff = staff.filter(is_active=False)
        else:
            staff = staff.none()

    page = pagination_context(request, staff, context_name="staff_users")
    rows = [{"user": user, "role": _role_name(user)} for user in page["staff_users"]]
    return render(
        request,
        "accounts/staff/list.html",
        {
            **page,
            "rows": rows,
            "query": query,
            "role": role,
            "status": status,
            "role_options": [{"value": "", "label": "All roles"}]
            + [{"value": name, "label": name} for name in BUSINESS_ROLES],
            "status_options": [
                {"value": "", "label": "All statuses"},
                {"value": "active", "label": "Active"},
                {"value": "inactive", "label": "Inactive"},
            ],
            "has_filters": bool(query or role or status),
            "breadcrumbs": [{"label": "Staff Accounts"}],
        },
    )


def _staff_detail_context(user, **overrides):
    role = _role_name(user)
    context = {
        "staff_user": user,
        "business_role": role,
        "profile_form": StaffUpdateForm(instance=user),
        "role_form": StaffRoleForm(initial={"role": role}),
        "password_form": AdminPasswordResetForm(user=user),
        "role_options": [{"value": name, "label": name} for name in BUSINESS_ROLES],
        "breadcrumbs": [
            {"label": "Staff Accounts", "url": reverse("accounts:staff-list")},
            {"label": user.username},
        ],
    }
    context.update(overrides)
    return context


@login_required
@require_http_methods(["GET", "POST"])
def staff_create(request):
    _require_owner_permission(request, "auth.add_user")
    form = StaffCreateForm(request.POST or None)
    if request.method == "POST":
        user = create_staff_user(actor=request.user, form=form)
        if user is not None:
            messages.success(request, f"Staff account {user.username} created successfully.")
            return redirect("accounts:staff-detail", pk=user.pk)
    return render(
        request,
        "accounts/staff/create.html",
        {
            "form": form,
            "role_options": [{"value": name, "label": name} for name in BUSINESS_ROLES],
            "breadcrumbs": [
                {"label": "Staff Accounts", "url": reverse("accounts:staff-list")},
                {"label": "Add staff account"},
            ],
        },
    )


@login_required
@require_GET
def staff_detail(request, pk):
    _require_owner_permission(request, "auth.view_user")
    return render(
        request,
        "accounts/staff/detail.html",
        _staff_detail_context(_staff_user(pk)),
    )


@login_required
@require_POST
def staff_update(request, pk):
    _require_owner_permission(request, "auth.change_user")
    user = _staff_user(pk)
    form = StaffUpdateForm(request.POST, instance=user)
    updated = update_staff_profile(actor=request.user, user_id=user.pk, form=form)
    if updated is not None:
        messages.success(request, "Staff account details updated.")
        return redirect("accounts:staff-detail", pk=user.pk)
    return render(
        request,
        "accounts/staff/detail.html",
        _staff_detail_context(user, profile_form=form),
        status=400,
    )


@login_required
@require_POST
def staff_role_update(request, pk):
    _require_owner_permission(request, "auth.change_user")
    user = _staff_user(pk)
    form = StaffRoleForm(request.POST)
    if form.is_valid():
        try:
            assign_staff_role(
                actor=request.user,
                user_id=user.pk,
                role=form.cleaned_data["role"],
            )
        except ValidationError as error:
            form.add_error("role", error)
        else:
            messages.success(request, "Business role updated.")
            return redirect("accounts:staff-detail", pk=user.pk)
    return render(
        request,
        "accounts/staff/detail.html",
        _staff_detail_context(user, role_form=form),
        status=400,
    )


@login_required
@require_POST
def staff_status_update(request, pk):
    _require_owner_permission(request, "auth.change_user")
    user = _staff_user(pk)
    form = StaffStatusForm(request.POST)
    if not form.is_valid():
        raise PermissionDenied
    try:
        updated = set_staff_active(
            actor=request.user,
            user_id=user.pk,
            is_active=form.cleaned_data["is_active"],
        )
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        action = "reactivated" if updated.is_active else "deactivated"
        messages.success(request, f"Staff account {action}.")
    return redirect("accounts:staff-detail", pk=user.pk)


@login_required
@require_POST
def staff_password_reset(request, pk):
    _require_owner_permission(request, "auth.change_user")
    user = _staff_user(pk)
    form = AdminPasswordResetForm(request.POST, user=user)
    if form.is_valid():
        reset_staff_password(
            actor=request.user,
            user_id=user.pk,
            password=form.cleaned_data["password1"],
        )
        messages.success(request, "Password reset successfully.")
        return redirect("accounts:staff-detail", pk=user.pk)
    return render(
        request,
        "accounts/staff/detail.html",
        _staff_detail_context(
            user,
            password_form=form,
            open_modal="reset-staff-password",
        ),
        status=400,
    )


def _matrix_context(selected_role):
    permissions = permission_objects()
    groups = {
        group.name: group
        for group in Group.objects.filter(name__in=BUSINESS_ROLES)
        .prefetch_related("permissions__content_type")
    }
    assigned = {}
    for role in BUSINESS_ROLES:
        if role == OWNER_ROLE:
            assigned[role] = set(APPROVED_PERMISSION_NAMES)
            continue
        group = groups.get(role)
        assigned[role] = {
            f"{permission.content_type.app_label}.{permission.codename}"
            for permission in group.permissions.all()
        } if group else set()

    domains = []
    for domain, capabilities in PERMISSION_GROUPS.items():
        rows = []
        for permission_name, label, description in capabilities:
            if permission_name not in permissions:
                continue
            rows.append(
                {
                    "permission": permission_name,
                    "label": label,
                    "description": description,
                    "role_states": [
                        {
                            "role": role,
                            "checked": permission_name in assigned[role],
                            "editable": (
                                role == selected_role
                                and permission_name in OPERATIONAL_PERMISSION_NAMES
                            ),
                            "disabled": (
                                role != selected_role
                                or permission_name not in OPERATIONAL_PERMISSION_NAMES
                            ),
                            "field_id": (
                                "permission-"
                                + permission_name.replace(".", "-")
                                + "-"
                                + ROLE_TO_SLUG[role]
                            ),
                        }
                        for role in BUSINESS_ROLES
                    ],
                }
            )
        if rows:
            domains.append({"name": domain, "capabilities": rows})
    return {
        "domains": domains,
        "business_roles": BUSINESS_ROLES,
        "selected_role": selected_role,
        "selected_slug": ROLE_TO_SLUG[selected_role],
        "role_tabs": [
            {"name": role, "slug": ROLE_TO_SLUG[role]}
            for role in OPERATIONAL_ROLES
        ],
    }


@login_required
@require_GET
def role_permissions(request):
    _require_owner_permission(request, "auth.view_group")
    selected_role = ROLE_SLUGS.get(request.GET.get("role", "pharmacist"))
    if selected_role not in OPERATIONAL_ROLES:
        selected_role = OPERATIONAL_ROLES[0]
    return render(
        request,
        "accounts/permissions/matrix.html",
        {
            **_matrix_context(selected_role),
            "breadcrumbs": [{"label": "Roles & Permissions"}],
        },
    )


@login_required
@require_POST
def role_permissions_update(request):
    _require_owner_permission(request, "auth.change_group")
    form = RolePermissionForm(
        request.POST,
        approved_permissions=OPERATIONAL_PERMISSION_NAMES,
    )
    if form.is_valid():
        try:
            update_role_permissions(
                actor=request.user,
                group_name=form.cleaned_data["role"],
                permission_names=form.cleaned_data["permissions"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, f"{form.cleaned_data['role']} permissions updated.")
            return redirect(
                f"{reverse('accounts:role-permissions')}?role={ROLE_TO_SLUG[form.cleaned_data['role']]}"
            )
    selected_role = form.cleaned_data.get("role") if hasattr(form, "cleaned_data") else None
    if selected_role not in OPERATIONAL_ROLES:
        selected_role = OPERATIONAL_ROLES[0]
    return render(
        request,
        "accounts/permissions/matrix.html",
        {
            **_matrix_context(selected_role),
            "permission_form": form,
            "breadcrumbs": [{"label": "Roles & Permissions"}],
        },
        status=400,
    )
