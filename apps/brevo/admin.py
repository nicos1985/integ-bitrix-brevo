from django import forms
from django.contrib import admin

from apps.brevo.models import BrevoAccount
from apps.core.encryption import encrypt_value


class BrevoAccountAdminForm(forms.ModelForm):
    new_api_key = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label="New API key",
        help_text="Enter a new Brevo API key to replace the stored one. Leave blank to keep the current one.",
    )

    class Meta:
        model = BrevoAccount
        fields = "__all__"

    def save(self, commit=True):
        instance = super().save(commit=False)
        new_key = self.cleaned_data.get("new_api_key")
        if new_key:
            instance.api_key_encrypted = encrypt_value(new_key)
        if commit:
            instance.save()
        return instance


@admin.register(BrevoAccount)
class BrevoAccountAdmin(admin.ModelAdmin):
    form = BrevoAccountAdminForm

    list_display = [
        "name", "tenant", "default_sender_email",
        "is_active", "updated_at",
    ]
    list_filter = ["is_active", "tenant"]
    search_fields = ["name", "tenant__slug", "default_sender_email"]
    ordering = ["name"]
    readonly_fields = ["api_key_encrypted", "created_at", "updated_at"]
    fieldsets = [
        (None, {"fields": ["tenant", "name", "is_active"]}),
        (
            "API key",
            {
                "fields": ["new_api_key", "api_key_encrypted"],
                "description": "The API key is stored encrypted. Use 'New API key' to set or rotate it.",
            },
        ),
        (
            "Sender defaults",
            {"fields": ["default_sender_email", "default_sender_name"]},
        ),
        (
            "Contact attribute mapping",
            {
                "fields": ["contact_attribute_map"],
                "description": (
                    "Map internal fields to the Brevo attribute names configured in this account. "
                    "Leave empty to use defaults (FIRSTNAME, LASTNAME, COMPANY, POSITION, SOURCE, BITRIX_ID). "
                    'Example for a Spanish account: {"first_name": "NOMBRE", "last_name": "APELLIDO", "company": "EMPRESA"}'
                ),
            },
        ),
        (
            "Webhook",
            {"fields": ["webhook_secret"], "classes": ["collapse"]},
        ),
        (
            "Timestamps",
            {"fields": ["created_at", "updated_at"], "classes": ["collapse"]},
        ),
    ]
