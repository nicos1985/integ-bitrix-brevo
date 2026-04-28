from django.contrib import admin

from apps.transactional.models import TransactionalEmailLog


@admin.register(TransactionalEmailLog)
class TransactionalEmailLogAdmin(admin.ModelAdmin):
    list_display = [
        "to_email", "template_id", "template_name", "status",
        "tenant", "brevo_message_id", "created_at",
    ]
    list_filter = ["status", "tenant"]
    search_fields = [
        "to_email", "to_name", "template_name",
        "brevo_message_id", "error_message",
    ]
    ordering = ["-created_at"]
    readonly_fields = [
        "tenant", "bitrix_portal", "brevo_account", "contact",
        "template_id", "template_name",
        "to_email", "to_name", "sender_email", "sender_name",
        "params", "attachments",
        "brevo_message_id", "status", "error_message",
        "created_at", "updated_at",
    ]
    date_hierarchy = "created_at"
    fieldsets = [
        (
            "Email",
            {
                "fields": [
                    "tenant", "bitrix_portal", "brevo_account", "contact",
                    "to_email", "to_name", "sender_email", "sender_name",
                ],
            },
        ),
        (
            "Template & params",
            {"fields": ["template_id", "template_name", "params", "attachments"]},
        ),
        (
            "Status",
            {"fields": ["status", "brevo_message_id", "error_message"]},
        ),
        (
            "Timestamps",
            {"fields": ["created_at", "updated_at"], "classes": ["collapse"]},
        ),
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
