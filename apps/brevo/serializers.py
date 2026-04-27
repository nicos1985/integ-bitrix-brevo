import logging

from rest_framework import serializers
from apps.brevo.models import BrevoAccount
from apps.core.encryption import encrypt_value

logger = logging.getLogger(__name__)


class BrevoAccountCreateSerializer(serializers.Serializer):
    tenant_slug = serializers.SlugField(write_only=True)
    name = serializers.CharField(max_length=255)
    api_key = serializers.CharField(write_only=True)
    default_sender_email = serializers.EmailField(required=False, allow_blank=True, default="")
    default_sender_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    webhook_secret = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    def validate_tenant_slug(self, value):
        from apps.tenants.models import Tenant
        try:
            return Tenant.objects.get(slug=value)
        except Tenant.DoesNotExist:
            raise serializers.ValidationError(f"Tenant '{value}' not found.")

    def create(self, validated_data):
        tenant = validated_data["tenant_slug"]
        account = BrevoAccount.objects.create(
            tenant=tenant,
            name=validated_data["name"],
            api_key_encrypted=encrypt_value(validated_data["api_key"]),
            default_sender_email=validated_data.get("default_sender_email") or "",
            default_sender_name=validated_data.get("default_sender_name") or "",
            webhook_secret=validated_data.get("webhook_secret") or "",
        )
        return account


class BrevoAccountReadSerializer(serializers.ModelSerializer):
    tenant_slug = serializers.SlugRelatedField(source="tenant", read_only=True, slug_field="slug")

    class Meta:
        model = BrevoAccount
        fields = [
            "id", "tenant_slug", "name",
            "default_sender_email", "default_sender_name",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = fields
