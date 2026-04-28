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

        # Bitrix24 requires PROPERTIES as a dict keyed by property name
        properties = {
            "TemplateId": {
                "Name": "Template ID",
                "Type": "int",
                "Required": "Y",
                "Multiple": "N",
                "Default": "",
            },
            "ToEmail": {
                "Name": "To Email",
                "Type": "string",
                "Required": "Y",
                "Multiple": "N",
                "Default": "",
            },
            "ToName": {
                "Name": "To Name",
                "Type": "string",
                "Required": "N",
                "Multiple": "N",
                "Default": "",
            },
            "SenderEmail": {
                "Name": "Sender Email",
                "Type": "string",
                "Required": "N",
                "Multiple": "N",
                "Default": "",
            },
            "SenderName": {
                "Name": "Sender Name",
                "Type": "string",
                "Required": "N",
                "Multiple": "N",
                "Default": "",
            },
            "Params": {
                "Name": "Template Params (JSON)",
                "Type": "text",
                "Required": "N",
                "Multiple": "N",
                "Default": "{}",
            },
            "Attachments": {
                "Name": "Attachments (JSON)",
                "Type": "text",
                "Required": "N",
                "Multiple": "N",
                "Default": "[]",
            },
        }

        try:
            result = self._client.register_bizproc_activity(
                code=ACTIVITY_CODE,
                handler_url=handler_url,
                auth_user_id=1,
                name="Send Brevo Email",
                description="Send a transactional email via Brevo",
                properties=properties,
            )
        except Exception as exc:
            # Activity already registered from a previous install — that's fine,
            # Bitrix does not allow updating PROPERTIES via REST after creation.
            logger.info(
                "Bizproc activity already registered for %s, skipping: %s",
                self.portal.domain, exc,
            )
            result = {"skipped": True}
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

        event_token = (
            payload.get("event_token")
            or payload.get("EVENT_TOKEN")
            or ""
        )

        # Bitrix24 sends properties as bracket notation: properties[TemplateId], etc.
        # Build a flat dict by extracting keys that start with 'properties['
        properties: dict = payload.get("PROPERTIES") or payload.get("properties") or {}
        if not properties or not isinstance(properties, dict) or not any(properties.values()):
            # Parse bracket notation from the flat payload QueryDict
            properties = {}
            for key, val in payload.items():
                if key.startswith("properties[") and key.endswith("]"):
                    prop_name = key[len("properties["):-1]
                    properties[prop_name] = val[0] if isinstance(val, list) else val

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
            if event_token:
                try:
                    self._client.complete_bizproc_activity(
                        event_token, log_message="TemplateId and ToEmail are required."
                    )
                except Exception:
                    pass
            return {"status": "error", "message": "TemplateId and ToEmail are required."}

        # Pick default brevo account for this portal's tenant
        brevo_account = (
            BrevoAccount.objects.filter(tenant=self.portal.tenant, is_active=True).first()
        )
        if not brevo_account:
            if event_token:
                try:
                    self._client.complete_bizproc_activity(
                        event_token, log_message="No active Brevo account found for tenant."
                    )
                except Exception:
                    pass
            return {"status": "error", "message": "No active Brevo account found for tenant."}

        sender: dict | None = None
        if sender_email:
            sender = {"email": sender_email, "name": sender_name}

        # Extract CRM entity from document_id bracket-notation keys
        # e.g. document_id[1]=CCrmDocumentDeal, document_id[2]=DEAL_100
        def _flat(key):
            v = payload.get(key)
            return (v[0] if isinstance(v, list) else v or "").strip() if v else ""

        doc_class = _flat("document_type[1]") or _flat("document_id[1]")
        doc_id_str = _flat("document_id[2]")  # e.g. "DEAL_100"
        entity_type_id = self._client._ENTITY_TYPE_IDS.get(doc_class)
        entity_id = doc_id_str.split("_")[-1] if "_" in doc_id_str else doc_id_str

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
            bitrix_entity_type=doc_class or None,
            bitrix_entity_id=entity_id or None,
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
            if event_token:
                try:
                    self._client.complete_bizproc_activity(
                        event_token,
                        return_values={"MessageId": log.brevo_message_id or ""},
                        log_message=f"Email sent via Brevo template {template_id}",
                    )
                except Exception as complete_exc:
                    logger.warning("Could not complete bizproc activity: %s", complete_exc)

            # Add timeline comment to the CRM entity
            if entity_type_id and entity_id:
                try:
                    self._client.add_timeline_comment(
                        entity_type_id,
                        entity_id,
                        f"Brevo: Email enviado (template {template_id} a {to_email})",
                    )
                except Exception as tl_exc:
                    logger.warning("Could not add timeline comment: %s", tl_exc)

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
            if event_token:
                try:
                    self._client.complete_bizproc_activity(
                        event_token, log_message=f"Error: {exc}"
                    )
                except Exception as complete_exc:
                    logger.warning("Could not complete bizproc activity on error: %s", complete_exc)
            return {"status": "error", "message": str(exc)}
