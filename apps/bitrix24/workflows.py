import logging

from django.conf import settings

from apps.bitrix24.clients import BitrixClient
from apps.sync.models import SyncLog

logger = logging.getLogger(__name__)

ACTIVITY_CODE = "brevo_send_email"


class WorkflowService:
    """Handles Bitrix24 bizproc activity registration and execution."""

    def __init__(self, portal):
        self.portal = portal
        self._client = BitrixClient(portal)

    def register_brevo_send_email_activity(self) -> dict:
        """Register the 'Send Brevo Email' activity with bizproc.activity.add."""
        base_url = settings.BITRIX_APP_BASE_URL.rstrip("/")
        handler_url = f"{base_url}/api/bitrix/workflows/brevo-send-email/"

        properties = [
            {
                "Name": "TemplateId",
                "Type": "int",
                "Required": "Y",
                "Multiple": "N",
                "Default": "",
                "Options": None,
            },
            {
                "Name": "ToEmail",
                "Type": "string",
                "Required": "Y",
                "Multiple": "N",
                "Default": "",
                "Options": None,
            },
            {
                "Name": "ToName",
                "Type": "string",
                "Required": "N",
                "Multiple": "N",
                "Default": "",
                "Options": None,
            },
            {
                "Name": "SenderEmail",
                "Type": "string",
                "Required": "N",
                "Multiple": "N",
                "Default": "",
                "Options": None,
            },
            {
                "Name": "SenderName",
                "Type": "string",
                "Required": "N",
                "Multiple": "N",
                "Default": "",
                "Options": None,
            },
            {
                "Name": "Params",
                "Type": "text",
                "Required": "N",
                "Multiple": "N",
                "Default": "{}",
                "Options": None,
            },
            {
                "Name": "Attachments",
                "Type": "text",
                "Required": "N",
                "Multiple": "N",
                "Default": "[]",
                "Options": None,
            },
        ]

        result = self._client.register_bizproc_activity(
            code=ACTIVITY_CODE,
            handler_url=handler_url,
            auth_user_id=1,
            name={"ru": "Отправить письмо Brevo", "en": "Send Brevo Email"},
            description={
                "ru": "Отправить транзакционное письмо через Brevo",
                "en": "Send a transactional email via Brevo",
            },
            properties=properties,
        )
        logger.info("Registered bizproc activity for portal %s", self.portal.domain)
        return result

    def handle_brevo_send_email_activity(self, payload: dict) -> dict:
        """
        Execute the workflow action: send an email via Brevo.
        Called when Bitrix24 triggers the workflow node.
        """
        import json
        from apps.brevo.models import BrevoAccount
        from apps.brevo.transactional import BrevoTransactionalService
        from apps.transactional.models import TransactionalEmailLog
        from apps.sync.models import SyncedContact

        properties = payload.get("PROPERTIES") or payload.get("properties") or {}
        template_id = int(properties.get("TemplateId") or properties.get("templateId") or 0)
        to_email = (properties.get("ToEmail") or properties.get("to_email") or "").strip()
        to_name = (properties.get("ToName") or properties.get("to_name") or "").strip() or None
        sender_email = (properties.get("SenderEmail") or "").strip() or None
        sender_name = (properties.get("SenderName") or "").strip() or None
        params_raw = properties.get("Params") or "{}"
        attachments_raw = properties.get("Attachments") or "[]"

        try:
            params = json.loads(params_raw) if isinstance(params_raw, str) else params_raw
        except json.JSONDecodeError:
            params = {}

        try:
            attachments = json.loads(attachments_raw) if isinstance(attachments_raw, str) else attachments_raw
        except json.JSONDecodeError:
            attachments = []

        if not template_id or not to_email:
            return {"status": "error", "message": "TemplateId and ToEmail are required."}

        # Pick default brevo account for this portal's tenant
        brevo_account = (
            BrevoAccount.objects.filter(tenant=self.portal.tenant, is_active=True).first()
        )
        if not brevo_account:
            return {"status": "error", "message": "No active Brevo account found for tenant."}

        sender: dict | None = None
        if sender_email:
            sender = {"email": sender_email, "name": sender_name}

        log = TransactionalEmailLog.objects.create(
            tenant=self.portal.tenant,
            bitrix_portal=self.portal,
            brevo_account=brevo_account,
            template_id=template_id,
            to_email=to_email,
            to_name=to_name,
            sender_email=sender_email,
            sender_name=sender_name,
            params=params,
            attachments=attachments,
            status=TransactionalEmailLog.STATUS_QUEUED,
        )

        # Link contact if exists
        try:
            contact = SyncedContact.objects.get(tenant=self.portal.tenant, email=to_email.lower())
            log.contact = contact
            log.save(update_fields=["contact"])
        except SyncedContact.DoesNotExist:
            pass

        try:
            service = BrevoTransactionalService(brevo_account)
            result = service.send_template_email(
                to_email=to_email,
                to_name=to_name,
                template_id=template_id,
                params=params,
                sender=sender,
                attachments=attachments or None,
            )
            log.brevo_message_id = result.get("messageId") or result.get("message-id")
            log.status = TransactionalEmailLog.STATUS_SENT
            log.save(update_fields=["brevo_message_id", "status", "updated_at"])

            SyncLog.objects.create(
                tenant=self.portal.tenant,
                contact=log.contact,
                source=SyncLog.SOURCE_BITRIX,
                direction=SyncLog.DIRECTION_TRANSACTIONAL,
                event_type="bizproc_brevo_email",
                status=SyncLog.STATUS_SUCCESS,
                message=f"Sent template {template_id} to {to_email}",
            )
            return {"status": "ok", "message_id": log.brevo_message_id}

        except Exception as exc:
            log.status = TransactionalEmailLog.STATUS_ERROR
            log.error_message = str(exc)
            log.save(update_fields=["status", "error_message", "updated_at"])

            SyncLog.objects.create(
                tenant=self.portal.tenant,
                source=SyncLog.SOURCE_BITRIX,
                direction=SyncLog.DIRECTION_TRANSACTIONAL,
                event_type="bizproc_brevo_email",
                status=SyncLog.STATUS_ERROR,
                message=str(exc),
            )
            return {"status": "error", "message": str(exc)}
