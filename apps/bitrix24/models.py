from django.db import models


class BitrixPortal(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="bitrix_portals",
    )

    domain = models.CharField(max_length=255, unique=True)
    member_id = models.CharField(max_length=255, unique=True, null=True, blank=True)

    client_id = models.CharField(max_length=255)
    client_secret_encrypted = models.TextField()

    access_token_encrypted = models.TextField(null=True, blank=True)
    refresh_token_encrypted = models.TextField(null=True, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)

    # Optional application-level token sent by Bitrix24 on event notifications
    application_token = models.CharField(max_length=255, null=True, blank=True)

    rest_endpoint = models.URLField(null=True, blank=True)
    installed_at = models.DateTimeField(null=True, blank=True)
    uninstalled_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["domain"]

    def __str__(self):
        return self.domain
