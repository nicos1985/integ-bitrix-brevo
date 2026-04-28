from django.db import models


class TransactionalEmailLog(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_SENT = "sent"
    STATUS_ERROR = "error"
    STATUS_DELIVERED = "delivered"
    STATUS_OPENED = "opened"
    STATUS_CLICKED = "clicked"
    STATUS_BOUNCED = "bounced"
    STATUS_UNSUBSCRIBED = "unsubscribed"

    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_SENT, "Sent"),
        (STATUS_ERROR, "Error"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_OPENED, "Opened"),
        (STATUS_CLICKED, "Clicked"),
        (STATUS_BOUNCED, "Bounced"),
        (STATUS_UNSUBSCRIBED, "Unsubscribed"),
    ]

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    bitrix_portal = models.ForeignKey(
        "bitrix24.BitrixPortal",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    brevo_account = models.ForeignKey(
        "brevo.BrevoAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    contact = models.ForeignKey(
        "sync.SyncedContact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    template_id = models.IntegerField()
    template_name = models.CharField(max_length=255, null=True, blank=True)

    to_email = models.EmailField()
    to_name = models.CharField(max_length=255, null=True, blank=True)
    sender_email = models.EmailField(null=True, blank=True)
    sender_name = models.CharField(max_length=255, null=True, blank=True)

    params = models.JSONField(default=dict, blank=True)
    attachments = models.JSONField(default=list, blank=True)

    # CRM entity that triggered the workflow (e.g. "deal" / "100", "contact" / "42")
    bitrix_entity_type = models.CharField(max_length=50, null=True, blank=True)
    bitrix_entity_id = models.CharField(max_length=50, null=True, blank=True)

    brevo_message_id = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=STATUS_QUEUED)

    error_message = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.status}] template={self.template_id} → {self.to_email}"
