from rest_framework import serializers


class TransactionalSendSerializer(serializers.Serializer):
    tenant_slug = serializers.SlugField()
    to_email = serializers.EmailField()
    to_name = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    template_id = serializers.IntegerField(min_value=1)
    sender = serializers.DictField(child=serializers.CharField(), required=False, default=dict)
    params = serializers.DictField(child=serializers.JSONField(), required=False, default=dict)
    attachments = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField()),
        required=False,
        default=list,
    )

    def validate_tenant_slug(self, value):
        from apps.tenants.models import Tenant
        try:
            return Tenant.objects.get(slug=value)
        except Tenant.DoesNotExist:
            raise serializers.ValidationError(f"Tenant '{value}' not found.")
