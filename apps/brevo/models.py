from django.db import models


class BrevoAccount(models.Model):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="brevo_accounts",
    )

    name = models.CharField(max_length=255)
    api_key_encrypted = models.TextField()

    default_sender_email = models.EmailField(null=True, blank=True)
    default_sender_name = models.CharField(max_length=255, null=True, blank=True)

    webhook_secret = models.CharField(max_length=255, null=True, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.tenant})"
