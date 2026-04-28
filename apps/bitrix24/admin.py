from django import forms
from django.contrib import admin
from django.utils.html import format_html

from apps.bitrix24.models import BitrixPortal
from apps.core.encryption import encrypt_value, decrypt_value


class BitrixPortalAdminForm(forms.ModelForm):
    """
    Custom form: exposes a plain-text `client_secret` input field.
    If provided, it overwrites client_secret_encrypted on save.
    Leave blank to keep the existing secret.
    """
    new_client_secret = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label="New client secret",
        help_text="Enter a new value to replace the stored secret. Leave blank to keep the current one.",
    )

    class Meta:
        model = BitrixPortal
        fields = "__all__"

    def save(self, commit=True):
        instance = super().save(commit=False)
        new_secret = self.cleaned_data.get("new_client_secret")
        if new_secret:
            instance.client_secret_encrypted = encrypt_value(new_secret)
        if commit:
            instance.save()
        return instance


@admin.register(BitrixPortal)
class BitrixPortalAdmin(admin.ModelAdmin):
    form = BitrixPortalAdminForm

    list_display = [
        "domain", "tenant", "client_id", "is_active",
        "installed_at", "updated_at",
    ]
    list_filter = ["is_active", "tenant"]
    search_fields = ["domain", "member_id", "client_id", "tenant__slug"]
    ordering = ["domain"]
    readonly_fields = [
        "client_secret_encrypted", "access_token_encrypted",
        "refresh_token_encrypted", "member_id", "application_token",
        "installed_at", "uninstalled_at", "created_at", "updated_at",
    ]
    fieldsets = [
        ("Identity", {"fields": ["tenant", "domain", "member_id", "is_active"]}),
        (
            "OAuth credentials",
            {
                "fields": [
                    "client_id",
                    "new_client_secret",
                    "client_secret_encrypted",
                ],
                "description": (
                    "client_secret is stored encrypted. Use 'New client secret' to update it. "
                    "Access/refresh tokens are managed automatically by the OAuth flow."
                ),
            },
        ),
        (
            "OAuth tokens (managed automatically)",
            {
                "fields": [
                    "access_token_encrypted",
                    "refresh_token_encrypted",
                    "token_expires_at",
                    "application_token",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Endpoint & timestamps",
            {
                "fields": [
                    "rest_endpoint",
                    "installed_at",
                    "uninstalled_at",
                    "created_at",
                    "updated_at",
                ],
                "classes": ["collapse"],
            },
        ),
    ]
