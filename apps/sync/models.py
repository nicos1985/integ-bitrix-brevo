from django.db import models


class SyncedContact(models.Model):
    SUBSCRIPTION_UNKNOWN = "unknown"
    SUBSCRIPTION_SUBSCRIBED = "subscribed"
    SUBSCRIPTION_UNSUBSCRIBED = "unsubscribed"
    SUBSCRIPTION_BLACKLISTED = "blacklisted"

    SUBSCRIPTION_CHOICES = [
        (SUBSCRIPTION_UNKNOWN, "Unknown"),
        (SUBSCRIPTION_SUBSCRIBED, "Subscribed"),
        (SUBSCRIPTION_UNSUBSCRIBED, "Unsubscribed"),
        (SUBSCRIPTION_BLACKLISTED, "Blacklisted"),
    ]

    DIRECTION_BITRIX_TO_BREVO = "bitrix_to_brevo"
    DIRECTION_BREVO_TO_BITRIX = "brevo_to_bitrix"
    DIRECTION_RECONCILE = "reconcile"

    DIRECTION_CHOICES = [
        (DIRECTION_BITRIX_TO_BREVO, "Bitrix to Brevo"),
        (DIRECTION_BREVO_TO_BITRIX, "Brevo to Bitrix"),
        (DIRECTION_RECONCILE, "Reconcile"),
    ]

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    bitrix_portal = models.ForeignKey("bitrix24.BitrixPortal", on_delete=models.CASCADE)
    brevo_account = models.ForeignKey("brevo.BrevoAccount", on_delete=models.CASCADE)

    email = models.EmailField(db_index=True)
    phone = models.CharField(max_length=50, null=True, blank=True)

    bitrix_contact_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    brevo_contact_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)

    first_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    company = models.CharField(max_length=255, null=True, blank=True)
    position = models.CharField(max_length=255, null=True, blank=True)
    source = models.CharField(max_length=255, null=True, blank=True)

    tags = models.JSONField(default=list, blank=True)
    brevo_lists = models.JSONField(default=list, blank=True)

    subscription_status = models.CharField(
        max_length=50,
        choices=SUBSCRIPTION_CHOICES,
        default=SUBSCRIPTION_UNKNOWN,
    )

    bitrix_updated_at = models.DateTimeField(null=True, blank=True)
    brevo_updated_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    last_sync_direction = models.CharField(
        max_length=50,
        choices=DIRECTION_CHOICES,
        null=True,
        blank=True,
    )

    sync_hash = models.CharField(max_length=128, null=True, blank=True)
    has_sync_error = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("tenant", "email")]
        ordering = ["email"]

    def __str__(self):
        return self.email


class SyncLog(models.Model):
    SOURCE_BITRIX = "bitrix"
    SOURCE_BREVO = "brevo"
    SOURCE_SYSTEM = "system"

    SOURCE_CHOICES = [
        (SOURCE_BITRIX, "Bitrix24"),
        (SOURCE_BREVO, "Brevo"),
        (SOURCE_SYSTEM, "System"),
    ]

    DIRECTION_BITRIX_TO_BREVO = "bitrix_to_brevo"
    DIRECTION_BREVO_TO_BITRIX = "brevo_to_bitrix"
    DIRECTION_TRANSACTIONAL = "transactional"
    DIRECTION_INSTALL = "install"
    DIRECTION_WEBHOOK = "webhook"

    DIRECTION_CHOICES = [
        (DIRECTION_BITRIX_TO_BREVO, "Bitrix to Brevo"),
        (DIRECTION_BREVO_TO_BITRIX, "Brevo to Bitrix"),
        (DIRECTION_TRANSACTIONAL, "Transactional"),
        (DIRECTION_INSTALL, "Install"),
        (DIRECTION_WEBHOOK, "Webhook"),
    ]

    STATUS_SUCCESS = "success"
    STATUS_IGNORED = "ignored"
    STATUS_ERROR = "error"
    STATUS_WARNING = "warning"

    STATUS_CHOICES = [
        (STATUS_SUCCESS, "Success"),
        (STATUS_IGNORED, "Ignored"),
        (STATUS_ERROR, "Error"),
        (STATUS_WARNING, "Warning"),
    ]

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    contact = models.ForeignKey(
        "sync.SyncedContact",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    source = models.CharField(max_length=50, choices=SOURCE_CHOICES)
    direction = models.CharField(max_length=50, choices=DIRECTION_CHOICES, null=True, blank=True)
    event_type = models.CharField(max_length=100)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES)

    external_id = models.CharField(max_length=255, null=True, blank=True)
    message = models.TextField(null=True, blank=True)

    request_payload = models.JSONField(null=True, blank=True)
    response_payload = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} [{self.status}] @ {self.created_at}"


class IntegrationEvent(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PROCESSED = "processed"
    STATUS_IGNORED = "ignored"
    STATUS_ERROR = "error"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSED, "Processed"),
        (STATUS_IGNORED, "Ignored"),
        (STATUS_ERROR, "Error"),
    ]

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)

    source = models.CharField(max_length=50)
    event_type = models.CharField(max_length=100)
    external_event_id = models.CharField(max_length=255, null=True, blank=True)

    dedupe_key = models.CharField(max_length=255, unique=True)
    payload = models.JSONField()

    processed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=STATUS_PENDING)

    error_message = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.source}:{self.event_type} [{self.status}]"
