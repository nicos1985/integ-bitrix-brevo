import logging
from datetime import datetime, timezone

from apps.core.utils import normalize_email, build_contact_hash
from apps.sync.models import SyncedContact, SyncLog, IntegrationEvent
from apps.brevo.contacts import BrevoContactService
from apps.brevo.clients import BrevoAPIError
from apps.bitrix24.clients import BitrixClient, BitrixAPIError

logger = logging.getLogger(__name__)


class SyncService:
    """
    Orchestrates bidirectional contact synchronisation between Bitrix24 and Brevo.
    """

    def __init__(self, portal, brevo_account):
        self.portal = portal
        self.brevo_account = brevo_account
        self.tenant = portal.tenant
        self._bitrix = BitrixClient(portal)
        self._brevo_contacts = BrevoContactService(brevo_account)

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def sync_from_bitrix_event(self, event_type: str, event_payload: dict) -> None:
        """
        Process a Bitrix24 CRM contact event (onCrmContactAdd / onCrmContactUpdate).
        Idempotency is guaranteed via IntegrationEvent.dedupe_key.
        """
        contact_id = str(
            event_payload.get("data", {}).get("FIELDS", {}).get("ID")
            or event_payload.get("OBJECT_ID")
            or event_payload.get("ID")
            or ""
        )
        if not contact_id:
            self._log(SyncLog.SOURCE_BITRIX, SyncLog.DIRECTION_BITRIX_TO_BREVO, event_type, SyncLog.STATUS_IGNORED,
                      message="No contact ID in event payload.")
            return

        dedupe_key = f"bitrix:{event_type}:{self.portal.member_id}:{contact_id}"
        event, created = IntegrationEvent.objects.get_or_create(
            dedupe_key=dedupe_key,
            defaults={
                "tenant": self.tenant,
                "source": "bitrix",
                "event_type": event_type,
                "external_event_id": contact_id,
                "payload": event_payload,
                "status": IntegrationEvent.STATUS_PENDING,
            },
        )
        if not created and event.status in (IntegrationEvent.STATUS_PROCESSED, IntegrationEvent.STATUS_IGNORED):
            logger.debug("Duplicate event ignored: %s", dedupe_key)
            return

        try:
            bitrix_contact = self._bitrix.get_contact(contact_id)
            if not bitrix_contact:
                event.status = IntegrationEvent.STATUS_IGNORED
                event.error_message = "Contact not found in Bitrix24."
                event.save(update_fields=["status", "error_message"])
                return

            self._sync_bitrix_contact_to_brevo(bitrix_contact)
            event.status = IntegrationEvent.STATUS_PROCESSED
            event.processed_at = datetime.now(tz=timezone.utc)
            event.save(update_fields=["status", "processed_at"])
        except Exception as exc:
            event.status = IntegrationEvent.STATUS_ERROR
            event.error_message = str(exc)
            event.save(update_fields=["status", "error_message"])
            logger.error("Error processing Bitrix event %s: %s", dedupe_key, exc)
            raise

    def sync_from_brevo_webhook(self, event_type: str, webhook_payload: dict) -> None:
        """
        Process a Brevo webhook event.
        """
        email = normalize_email(webhook_payload.get("email"))
        if not email:
            self._log(SyncLog.SOURCE_BREVO, SyncLog.DIRECTION_WEBHOOK, event_type, SyncLog.STATUS_IGNORED,
                      message="No email in webhook payload.")
            return

        dedupe_key = (
            f"brevo:{event_type}:{self.brevo_account.id}:{email}:"
            f"{webhook_payload.get('message-id', '')}:{webhook_payload.get('date', '')}"
        )
        event, created = IntegrationEvent.objects.get_or_create(
            dedupe_key=dedupe_key,
            defaults={
                "tenant": self.tenant,
                "source": "brevo",
                "event_type": event_type,
                "payload": webhook_payload,
                "status": IntegrationEvent.STATUS_PENDING,
            },
        )
        if not created and event.status in (IntegrationEvent.STATUS_PROCESSED, IntegrationEvent.STATUS_IGNORED):
            logger.debug("Duplicate Brevo webhook ignored: %s", dedupe_key)
            return

        try:
            if event_type in ("unsubscribe", "hardBounce", "spam", "blocked"):
                self._handle_brevo_unsubscribe(email, event_type, webhook_payload)
            elif event_type in ("contact_updated", "contact_added_to_list"):
                self._handle_brevo_contact_update(email, event_type, webhook_payload)
            elif event_type in ("delivered", "opened", "click", "bounce"):
                self._handle_brevo_transactional_status(email, event_type, webhook_payload)
            else:
                logger.debug("Unhandled Brevo event type: %s", event_type)

            event.status = IntegrationEvent.STATUS_PROCESSED
            event.processed_at = datetime.now(tz=timezone.utc)
            event.save(update_fields=["status", "processed_at"])
        except Exception as exc:
            event.status = IntegrationEvent.STATUS_ERROR
            event.error_message = str(exc)
            event.save(update_fields=["status", "error_message"])
            logger.error("Error processing Brevo webhook %s: %s", dedupe_key, exc)
            raise

    def sync_contact_bitrix_to_brevo(self, synced_contact) -> None:
        """
        Push a local SyncedContact to Brevo.
        """
        self._push_to_brevo(synced_contact)

    def sync_contact_brevo_to_bitrix(self, synced_contact) -> None:
        """
        Push a local SyncedContact to Bitrix24.
        """
        self._push_to_bitrix(synced_contact)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _sync_bitrix_contact_to_brevo(self, bitrix_contact: dict) -> None:
        email = self._extract_email(bitrix_contact)
        if not email:
            self._log(SyncLog.SOURCE_BITRIX, SyncLog.DIRECTION_BITRIX_TO_BREVO, "contact_sync",
                      SyncLog.STATUS_IGNORED, message="Contact has no email.")
            return

        contact, _ = SyncedContact.objects.get_or_create(
            tenant=self.tenant,
            email=email,
            defaults={
                "bitrix_portal": self.portal,
                "brevo_account": self.brevo_account,
            },
        )

        self._map_bitrix_to_contact(bitrix_contact, contact)

        incoming_hash = build_contact_hash(self._contact_hashable_fields(contact))
        if incoming_hash == contact.sync_hash and contact.last_sync_direction == SyncedContact.DIRECTION_BITRIX_TO_BREVO:
            self._log(SyncLog.SOURCE_BITRIX, SyncLog.DIRECTION_BITRIX_TO_BREVO, "contact_sync",
                      SyncLog.STATUS_IGNORED, contact=contact, message="No field changes detected (hash match).")
            return

        self._push_to_brevo(contact)

    def _push_to_brevo(self, contact) -> None:
        try:
            self._brevo_contacts.create_or_update(contact)
            contact.last_sync_direction = SyncedContact.DIRECTION_BITRIX_TO_BREVO
            contact.last_synced_at = datetime.now(tz=timezone.utc)
            contact.sync_hash = build_contact_hash(self._contact_hashable_fields(contact))
            contact.has_sync_error = False
            contact.save()
            self._log(SyncLog.SOURCE_BITRIX, SyncLog.DIRECTION_BITRIX_TO_BREVO, "contact_sync",
                      SyncLog.STATUS_SUCCESS, contact=contact)
        except BrevoAPIError as exc:
            contact.has_sync_error = True
            contact.save(update_fields=["has_sync_error", "updated_at"])
            self._log(SyncLog.SOURCE_BITRIX, SyncLog.DIRECTION_BITRIX_TO_BREVO, "contact_sync",
                      SyncLog.STATUS_ERROR, contact=contact, message=str(exc))
            raise

    def _push_to_bitrix(self, contact) -> None:
        bitrix_data = self._map_contact_to_bitrix(contact)
        try:
            if contact.bitrix_contact_id:
                self._bitrix.update_contact(contact.bitrix_contact_id, bitrix_data)
            else:
                result = self._bitrix.create_contact(bitrix_data)
                contact.bitrix_contact_id = str(result)
            contact.last_sync_direction = SyncedContact.DIRECTION_BREVO_TO_BITRIX
            contact.last_synced_at = datetime.now(tz=timezone.utc)
            contact.sync_hash = build_contact_hash(self._contact_hashable_fields(contact))
            contact.has_sync_error = False
            contact.save()
            self._log(SyncLog.SOURCE_BREVO, SyncLog.DIRECTION_BREVO_TO_BITRIX, "contact_sync",
                      SyncLog.STATUS_SUCCESS, contact=contact)
        except BitrixAPIError as exc:
            contact.has_sync_error = True
            contact.save(update_fields=["has_sync_error", "updated_at"])
            self._log(SyncLog.SOURCE_BREVO, SyncLog.DIRECTION_BREVO_TO_BITRIX, "contact_sync",
                      SyncLog.STATUS_ERROR, contact=contact, message=str(exc))
            raise

    def _handle_brevo_unsubscribe(self, email: str, event_type: str, payload: dict) -> None:
        """Update local subscription_status only. Never touch Bitrix24."""
        from apps.sync.models import SyncedContact
        try:
            contact = SyncedContact.objects.get(tenant=self.tenant, email=email)
        except SyncedContact.DoesNotExist:
            self._log(SyncLog.SOURCE_BREVO, SyncLog.DIRECTION_WEBHOOK, event_type,
                      SyncLog.STATUS_IGNORED, message=f"No local contact for {email}.")
            return

        new_status = (
            SyncedContact.SUBSCRIPTION_BLACKLISTED
            if event_type in ("hardBounce", "spam", "blocked")
            else SyncedContact.SUBSCRIPTION_UNSUBSCRIBED
        )
        contact.subscription_status = new_status
        contact.brevo_updated_at = datetime.now(tz=timezone.utc)
        contact.save(update_fields=["subscription_status", "brevo_updated_at", "updated_at"])
        self._log(SyncLog.SOURCE_BREVO, SyncLog.DIRECTION_WEBHOOK, event_type,
                  SyncLog.STATUS_SUCCESS, contact=contact,
                  message=f"Subscription status updated to {new_status}.")

    def _handle_brevo_contact_update(self, email: str, event_type: str, payload: dict) -> None:
        """Brevo contact_updated — update local record and optionally push to Bitrix24."""
        try:
            contact = SyncedContact.objects.get(tenant=self.tenant, email=email)
        except SyncedContact.DoesNotExist:
            # Create a new contact locally and push to Bitrix24
            contact = SyncedContact(
                tenant=self.tenant,
                email=email,
                bitrix_portal=self.portal,
                brevo_account=self.brevo_account,
            )
            contact.brevo_updated_at = datetime.now(tz=timezone.utc)
            contact.save()
            self._push_to_bitrix(contact)
            return

        contact.brevo_updated_at = datetime.now(tz=timezone.utc)
        contact.save(update_fields=["brevo_updated_at", "updated_at"])
        self._resolve_and_push(contact)

    def _handle_brevo_transactional_status(self, email: str, event_type: str, payload: dict) -> None:
        """Update TransactionalEmailLog status based on Brevo transactional webhook."""
        from apps.transactional.models import TransactionalEmailLog
        message_id = payload.get("message-id") or payload.get("messageId")
        if not message_id:
            return
        STATUS_MAP = {
            "delivered": TransactionalEmailLog.STATUS_DELIVERED,
            "opened": TransactionalEmailLog.STATUS_OPENED,
            "click": TransactionalEmailLog.STATUS_CLICKED,
            "bounce": TransactionalEmailLog.STATUS_BOUNCED,
        }
        new_status = STATUS_MAP.get(event_type)
        if new_status:
            TransactionalEmailLog.objects.filter(brevo_message_id=message_id).update(status=new_status)

    def _resolve_and_push(self, contact) -> None:
        """Apply conflict resolution: whoever was updated most recently wins."""
        bitrix_ts = contact.bitrix_updated_at
        brevo_ts = contact.brevo_updated_at
        if brevo_ts and (not bitrix_ts or brevo_ts > bitrix_ts):
            self._push_to_bitrix(contact)
        else:
            self._push_to_brevo(contact)

    # ------------------------------------------------------------------
    # Field mapping helpers
    # ------------------------------------------------------------------

    def _extract_email(self, bitrix_contact: dict) -> str | None:
        emails = bitrix_contact.get("EMAIL") or []
        if isinstance(emails, list):
            for item in emails:
                val = item.get("VALUE", "")
                if val:
                    return normalize_email(val)
        return None

    def _map_bitrix_to_contact(self, bc: dict, contact) -> None:
        contact.bitrix_contact_id = str(bc.get("ID", "") or contact.bitrix_contact_id or "")
        contact.first_name = bc.get("NAME") or contact.first_name
        contact.last_name = bc.get("LAST_NAME") or contact.last_name
        contact.company = bc.get("COMPANY_TITLE") or contact.company
        contact.position = bc.get("POST") or contact.position
        contact.source = str(bc.get("SOURCE_ID", "") or bc.get("SOURCE_DESCRIPTION", "")) or contact.source

        phones = bc.get("PHONE") or []
        if isinstance(phones, list) and phones:
            contact.phone = phones[0].get("VALUE", "") or contact.phone

        date_modify = bc.get("DATE_MODIFY")
        if date_modify:
            try:
                contact.bitrix_updated_at = datetime.fromisoformat(date_modify.replace("T", " ").split("+")[0]).replace(tzinfo=timezone.utc)
            except (ValueError, AttributeError):
                pass
        contact.save()

    @staticmethod
    def _map_contact_to_bitrix(contact) -> dict:
        fields: dict = {}
        if contact.first_name:
            fields["NAME"] = contact.first_name
        if contact.last_name:
            fields["LAST_NAME"] = contact.last_name
        if contact.email:
            fields["EMAIL"] = [{"VALUE": contact.email, "VALUE_TYPE": "WORK"}]
        if contact.phone:
            fields["PHONE"] = [{"VALUE": contact.phone, "VALUE_TYPE": "WORK"}]
        if contact.company:
            fields["COMPANY_TITLE"] = contact.company
        if contact.position:
            fields["POST"] = contact.position
        return fields

    @staticmethod
    def _contact_hashable_fields(contact) -> dict:
        return {
            "email": contact.email,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "phone": contact.phone,
            "company": contact.company,
            "position": contact.position,
            "source": contact.source,
        }

    # ------------------------------------------------------------------
    # Logging helper
    # ------------------------------------------------------------------

    def _log(
        self,
        source: str,
        direction: str,
        event_type: str,
        status: str,
        contact=None,
        message: str | None = None,
        request_payload: dict | None = None,
        response_payload: dict | None = None,
    ) -> None:
        SyncLog.objects.create(
            tenant=self.tenant,
            contact=contact,
            source=source,
            direction=direction,
            event_type=event_type,
            status=status,
            message=message,
            request_payload=request_payload,
            response_payload=response_payload,
        )
