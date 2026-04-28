from django.db import models


# Default mapping: our internal field → Brevo attribute name
# Can be overridden per account in contact_attribute_map
DEFAULT_CONTACT_ATTRIBUTE_MAP = {
    "first_name": "FIRSTNAME",
    "last_name": "LASTNAME",
    "company": "COMPANY",
    "position": "POSITION",
    "source": "SOURCE",
    "bitrix_id": "BITRIX_ID",
}


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

    # Maps internal field names to the actual Brevo attribute names for this account.
    # Leave empty to use the defaults (FIRSTNAME, LASTNAME, etc.)
    # Example for a Spanish account: {"first_name": "NOMBRE", "last_name": "APELLIDO"}
    contact_attribute_map = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Map internal fields to Brevo attribute names for this account. "
            "Leave empty to use defaults. "
            "Keys: first_name, last_name, company, position, source, bitrix_id. "
            'Example: {"first_name": "NOMBRE", "last_name": "APELLIDO"}'
        ),
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.tenant})"

    def get_attribute_map(self) -> dict:
        """Return merged map: defaults overridden by account-specific values."""
        merged = dict(DEFAULT_CONTACT_ATTRIBUTE_MAP)
        merged.update(self.contact_attribute_map or {})
        return merged
