from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("staff/", views.staff_list, name="staff-list"),
    path("staff/new/", views.staff_create, name="staff-create"),
    path("staff/<int:pk>/", views.staff_detail, name="staff-detail"),
    path("staff/<int:pk>/update/", views.staff_update, name="staff-update"),
    path("staff/<int:pk>/role/", views.staff_role_update, name="staff-role-update"),
    path("staff/<int:pk>/status/", views.staff_status_update, name="staff-status-update"),
    path("staff/<int:pk>/reset-password/", views.staff_password_reset, name="staff-password-reset"),
    path("roles-permissions/", views.role_permissions, name="role-permissions"),
    path("roles-permissions/update/", views.role_permissions_update, name="role-permissions-update"),
]
