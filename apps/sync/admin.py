from django.contrib import admin

from apps.sync.models import IntegrationEvent, SyncedContact, SyncLog


@admin.register(SyncedContact)
class SyncedContactAdmin(admin.ModelAdmin):
    list_display = [
        "email", "tenant", "bitrix_portal", "subscription_status",
        "has_sync_error", "last_synced_at",
    ]
    list_filter = [
        "subscription_status", "has_sync_error",
        "last_sync_direction", "tenant",
    ]
    search_fields = [
        "email", "first_name", "last_name", "phone",
        "bitrix_contact_id", "brevo_contact_id",
    ]
    ordering = ["email"]
    readonly_fields = [
        "sync_hash", "bitrix_updated_at", "brevo_updated_at",
        "last_synced_at", "last_sync_direction", "created_at", "updated_at",
    ]
    fieldsets = [
        (
            "Identity",
            {
                "fields": [
                    "tenant", "bitrix_portal", "brevo_account",
                    "email", "phone", "first_name", "last_name",
                    "company", "position", "source",
                ],
            },
        ),
        (
            "External IDs",
            {"fields": ["bitrix_contact_id", "brevo_contact_id"]},
        ),
        (
            "Subscription & lists",
            {"fields": ["subscription_status", "tags", "brevo_lists"]},
        ),
        (
            "Sync state",
            {
                "fields": [
                    "has_sync_error", "last_sync_direction",
                    "last_synced_at", "bitrix_updated_at",
                    "brevo_updated_at", "sync_hash",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Timestamps",
            {"fields": ["created_at", "updated_at"], "classes": ["collapse"]},
        ),
    ]


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = [
        "event_type", "status", "source", "direction",
        "tenant", "external_id", "created_at",
    ]
    list_filter = ["status", "source", "direction", "tenant"]
    search_fields = ["event_type", "external_id", "message"]
    ordering = ["-created_at"]
    readonly_fields = [
        "tenant", "contact", "source", "direction", "event_type",
        "status", "external_id", "message",
        "request_payload", "response_payload", "created_at",
    ]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(IntegrationEvent)
class IntegrationEventAdmin(admin.ModelAdmin):
    list_display = [
        "event_type", "source", "status", "tenant",
        "external_event_id", "created_at",
    ]
    list_filter = ["status", "source", "tenant"]
    search_fields = ["event_type", "external_event_id", "dedupe_key"]
    ordering = ["-created_at"]
    readonly_fields = [
        "tenant", "source", "event_type", "external_event_id",
        "dedupe_key", "payload", "processed_at", "status",
        "error_message", "created_at",
    ]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
