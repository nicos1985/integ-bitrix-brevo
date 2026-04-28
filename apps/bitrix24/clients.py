import logging
import time
from datetime import datetime, timezone

import requests

from apps.core.encryption import decrypt_value
from apps.bitrix24.oauth import BitrixOAuthService, BitrixOAuthError

logger = logging.getLogger(__name__)


class BitrixAPIError(Exception):
    pass


class BitrixClient:
    """
    REST client for Bitrix24.
    Automatically refreshes the access token when it expires.
    """

    def __init__(self, portal):
        self.portal = portal
        self._oauth_service = BitrixOAuthService()

    def _get_base_url(self) -> str:
        if self.portal.rest_endpoint:
            # rest_endpoint stored as full base, e.g. "https://domain.bitrix24.com/rest/"
            return self.portal.rest_endpoint.rstrip("/")
        return f"https://{self.portal.domain}/rest"

    def _get_access_token(self) -> str:
        now = datetime.now(tz=timezone.utc)
        # Refresh proactively if expires in less than 60 seconds
        if self.portal.token_expires_at and self.portal.token_expires_at <= now:
            self._oauth_service.refresh_access_token(self.portal)
            self.portal.refresh_from_db()
        return decrypt_value(self.portal.access_token_encrypted) or ""

    def call(self, method: str, params: dict | None = None) -> dict:
        """
        Call a Bitrix24 REST method.
        Returns the 'result' portion of the response dict.
        Raises BitrixAPIError on failure.
        """
        url = f"{self._get_base_url()}/{method}.json"
        token = self._get_access_token()
        payload = dict(params or {})
        payload["auth"] = token

        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, timeout=20)
            except requests.Timeout:
                if attempt == 2:
                    raise BitrixAPIError(f"Timeout calling {method} after 3 attempts.")
                time.sleep(2 ** attempt)
                continue

            if resp.status_code == 401:
                # Token rejected — try one refresh then retry
                try:
                    self._oauth_service.refresh_access_token(self.portal)
                    self.portal.refresh_from_db()
                    token = decrypt_value(self.portal.access_token_encrypted) or ""
                    payload["auth"] = token
                    continue
                except BitrixOAuthError as exc:
                    raise BitrixAPIError(str(exc)) from exc

            if resp.status_code == 429:
                # Rate limited
                retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                logger.warning("Bitrix rate limit hit. Waiting %s seconds.", retry_after)
                time.sleep(retry_after)
                continue

            if not resp.ok:
                body = ""
                try:
                    body = resp.json()
                except Exception:
                    body = resp.text[:500]
                raise BitrixAPIError(
                    f"HTTP {resp.status_code} calling {method}: {body}"
                )

            data = resp.json()
            if "error" in data:
                raise BitrixAPIError(
                    f"Bitrix error calling {method}: {data.get('error')} — {data.get('error_description')}"
                )

            return data.get("result", data)

        raise BitrixAPIError(f"Failed to call {method} after 3 attempts.")

    # -----------------------------------------------------------------
    # CRM helpers
    # -----------------------------------------------------------------

    def get_contact(self, contact_id: int | str) -> dict | None:
        try:
            return self.call("crm.contact.get", {"id": contact_id})
        except BitrixAPIError as exc:
            logger.warning("Could not fetch contact %s: %s", contact_id, exc)
            return None

    def find_contact_by_email(self, email: str) -> dict | None:
        result = self.call(
            "crm.contact.list",
            {
                "filter": {"EMAIL": email},
                "select": ["ID", "NAME", "LAST_NAME", "EMAIL", "PHONE", "COMPANY_TITLE", "POST", "SOURCE_ID", "DATE_MODIFY"],
            },
        )
        items = result if isinstance(result, list) else result.get("result", [])
        return items[0] if items else None

    def list_contacts(self, start: int = 0, limit: int = 50) -> tuple[list, int]:
        """Returns (contacts_list, next_start) for pagination. next_start=0 means done."""
        result = self.call(
            "crm.contact.list",
            {
                "select": ["ID", "NAME", "LAST_NAME", "EMAIL", "PHONE", "COMPANY_TITLE", "POST", "SOURCE_ID", "DATE_MODIFY"],
                "start": start,
            },
        )
        if isinstance(result, dict):
            items = result.get("result", [])
            next_start = result.get("next", 0)
        else:
            items = result
            next_start = 0
        return items, next_start

    def create_contact(self, data: dict) -> dict:
        return self.call("crm.contact.add", {"fields": data})

    def update_contact(self, contact_id: int | str, data: dict) -> dict:
        return self.call("crm.contact.update", {"id": contact_id, "fields": data})

    # -----------------------------------------------------------------
    # Event registration
    # -----------------------------------------------------------------

    def register_event(self, event_name: str, handler_url: str) -> dict:
        # Unbind first to avoid "already registered" 400 on reinstalls
        try:
            self.call("event.unbind", {"event": event_name, "handler": handler_url})
        except BitrixAPIError:
            pass  # Not bound yet — that's fine
        return self.call("event.bind", {"event": event_name, "handler": handler_url})

    # -----------------------------------------------------------------
    # Bizproc activity registration
    # -----------------------------------------------------------------

    def register_bizproc_activity(
        self,
        code: str,
        handler_url: str,
        auth_user_id: int,
        name: str,
        description: str,
        properties: list[dict] | None = None,
    ) -> dict:
        params = {
            "CODE": code,
            "HANDLER": handler_url,
            "AUTH_USER_ID": auth_user_id,
            "NAME": name,
            "DESCRIPTION": description,
            "USE_SUBSCRIPTION": "Y",
            "PROPERTIES": properties or [],
        }
        return self.call("bizproc.activity.add", params)

    # Maps Bitrix24 document class names to numeric CRM entity type IDs
    _ENTITY_TYPE_IDS = {
        "CCrmDocumentLead": 1,
        "CCrmDocumentDeal": 2,
        "CCrmDocumentContact": 3,
        "CCrmDocumentCompany": 4,
    }

    def add_timeline_comment(self, entity_type_id: int, entity_id: int | str, comment: str) -> dict:
        """Add a comment to the timeline of a CRM entity (deal, contact, etc.)."""
        return self.call("crm.timeline.comment.add", {
            "fields": {
                "ENTITY_TYPE_ID": entity_type_id,
                "ENTITY_ID": int(entity_id),
                "COMMENT": comment,
            }
        })

    def complete_bizproc_activity(
        self,
        event_token: str,
        return_values: dict | None = None,
        log_message: str = "",
    ) -> dict:
        """Signal Bitrix24 that an async bizproc activity has finished.

        Bitrix24 uses bizproc.event.send (not bizproc.activity.complete)
        to unblock a workflow activity registered with USE_SUBSCRIPTION=Y.
        """
        params: dict = {"EVENT_TOKEN": event_token}
        if return_values:
            params["RETURN_VALUES"] = return_values
        if log_message:
            params["LOG_MESSAGE"] = log_message
        return self.call("bizproc.event.send", params)
