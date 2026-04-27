import logging

from apps.brevo.clients import BrevoClient, BrevoAPIError
from apps.core.utils import normalize_email

logger = logging.getLogger(__name__)


class BrevoContactService:
    """
    Handles contact-related Brevo API operations.
    All methods receive the BrevoAccount model instance as context.
    """

    def __init__(self, account):
        self.account = account
        self._client = BrevoClient(account)

    def get_by_email(self, email: str) -> dict | None:
        """Fetch a Brevo contact by email. Returns None if not found."""
        email = normalize_email(email)
        try:
            return self._client.request("GET", f"/contacts/{email}")
        except BrevoAPIError as exc:
            if exc.status_code == 404:
                return None
            raise

    def create_or_update(self, contact) -> dict:
        """
        Upsert a SyncedContact into Brevo.
        Uses updateEnabled=true so a single call handles both create and update.
        """
        email = normalize_email(contact.email)
        attributes = self._build_attributes(contact)
        payload = {
            "email": email,
            "attributes": attributes,
            "updateEnabled": True,
        }
        if contact.brevo_lists:
            payload["listIds"] = [int(lid) for lid in contact.brevo_lists]

        result = self._client.request("POST", "/contacts", json=payload)
        return result or {}

    def add_to_lists(self, email: str, list_ids: list[int]) -> None:
        """Add a contact to one or more Brevo lists."""
        if not list_ids:
            return
        email = normalize_email(email)
        for list_id in list_ids:
            try:
                self._client.request(
                    "POST",
                    f"/contacts/lists/{list_id}/contacts/add",
                    json={"emails": [email]},
                )
            except BrevoAPIError as exc:
                logger.warning("Could not add %s to Brevo list %s: %s", email, list_id, exc)

    def remove_from_lists(self, email: str, list_ids: list[int]) -> None:
        """Remove a contact from one or more Brevo lists."""
        if not list_ids:
            return
        email = normalize_email(email)
        for list_id in list_ids:
            try:
                self._client.request(
                    "POST",
                    f"/contacts/lists/{list_id}/contacts/remove",
                    json={"emails": [email]},
                )
            except BrevoAPIError as exc:
                logger.warning("Could not remove %s from Brevo list %s: %s", email, list_id, exc)

    def get_subscription_status(self, email: str) -> str:
        """
        Returns 'subscribed', 'unsubscribed', or 'blacklisted' based on Brevo data.
        Falls back to 'unknown' if the contact does not exist.
        """
        from apps.sync.models import SyncedContact
        contact_data = self.get_by_email(email)
        if not contact_data:
            return SyncedContact.SUBSCRIPTION_UNKNOWN
        if contact_data.get("emailBlacklisted"):
            return SyncedContact.SUBSCRIPTION_BLACKLISTED
        if not contact_data.get("emailBlacklisted") and contact_data.get("listIds"):
            return SyncedContact.SUBSCRIPTION_SUBSCRIBED
        return SyncedContact.SUBSCRIPTION_UNKNOWN

    def list_all_contacts(self, limit: int = 500, offset: int = 0) -> list[dict]:
        """Fetch a page of Brevo contacts."""
        result = self._client.request("GET", "/contacts", params={"limit": limit, "offset": offset})
        return (result or {}).get("contacts", [])

    # -----------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------

    @staticmethod
    def _build_attributes(contact) -> dict:
        attrs: dict = {}
        if contact.first_name:
            attrs["FIRSTNAME"] = contact.first_name
        if contact.last_name:
            attrs["LASTNAME"] = contact.last_name
        if contact.phone:
            attrs["SMS"] = contact.phone
        if contact.company:
            attrs["COMPANY"] = contact.company
        if contact.position:
            attrs["POSITION"] = contact.position
        if contact.source:
            attrs["SOURCE"] = contact.source
        if contact.bitrix_contact_id:
            attrs["BITRIX_ID"] = contact.bitrix_contact_id
        return attrs
