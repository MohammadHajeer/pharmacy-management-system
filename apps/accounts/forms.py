from django import forms
from django.contrib.auth import get_user_model, password_validation

from .permissions import BUSINESS_ROLES


User = get_user_model()
ROLE_CHOICES = tuple((role, role) for role in BUSINESS_ROLES)


class PasswordConfirmationMixin:
    password_field_name = "password1"

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get(self.password_field_name)
        confirmation = cleaned_data.get("password2")
        if password and confirmation and password != confirmation:
            self.add_error("password2", "The two password fields do not match.")
        if password:
            try:
                password_validation.validate_password(password, self.password_user)
            except forms.ValidationError as error:
                self.add_error(self.password_field_name, error)
        return cleaned_data


class StaffCreateForm(PasswordConfirmationMixin, forms.ModelForm):
    role = forms.ChoiceField(choices=ROLE_CHOICES)
    password1 = forms.CharField(strip=False)
    password2 = forms.CharField(strip=False)
    is_active = forms.BooleanField(required=False, initial=True)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active"]

    @property
    def password_user(self):
        user = self.instance
        for field in ("username", "first_name", "last_name", "email"):
            if field in self.cleaned_data:
                setattr(user, field, self.cleaned_data[field])
        return user


class StaffUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]


class StaffRoleForm(forms.Form):
    role = forms.ChoiceField(choices=ROLE_CHOICES)


class StaffStatusForm(forms.Form):
    is_active = forms.BooleanField(required=False)


class AdminPasswordResetForm(PasswordConfirmationMixin, forms.Form):
    password1 = forms.CharField(strip=False)
    password2 = forms.CharField(strip=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.password_user = user


class RolePermissionForm(forms.Form):
    role = forms.ChoiceField(
        choices=tuple((role, role) for role in BUSINESS_ROLES if role != "Owner / Admin")
    )
    permissions = forms.MultipleChoiceField(required=False)

    def __init__(self, *args, approved_permissions, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["permissions"].choices = tuple(
            (permission_name, permission_name)
            for permission_name in sorted(approved_permissions)
        )
