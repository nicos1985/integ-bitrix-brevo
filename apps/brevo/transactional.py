import logging

from apps.brevo.clients import BrevoClient, BrevoAPIError

logger = logging.getLogger(__name__)


class BrevoTransactionalService:
    """Handles template listing and transactional email sending via Brevo."""

    def __init__(self, account):
        self.account = account
        self._client = BrevoClient(account)

    def list_templates(self, active_only: bool = True) -> list[dict]:
        """Return SMTP templates. Pass active_only=True to filter by templateStatus=true."""
        params = {"limit": 50, "offset": 0}
        if active_only:
            params["templateStatus"] = "true"

        templates: list[dict] = []
        while True:
            result = self._client.request("GET", "/smtp/templates", params=params)
            page = (result or {}).get("templates", [])
            templates.extend(page)
            if len(page) < params["limit"]:
                break
            params["offset"] += params["limit"]  # type: ignore[operator]
        return templates

    def preview_template(self, template_id: int, params: dict | None = None) -> dict:
        """Preview a Brevo template with optional params."""
        payload: dict = {}
        if params:
            payload["params"] = params
        return self._client.request("POST", f"/smtp/templates/{template_id}/sendTest", json=payload) or {}

    def send_template_email(
        self,
        to_email: str,
        to_name: str | None,
        template_id: int,
        params: dict | None = None,
        sender: dict | None = None,
        attachments: list[dict] | None = None,
    ) -> dict:
        """
        Send a transactional email using a Brevo template.

        Args:
            to_email: Recipient email address.
            to_name: Recipient display name.
            template_id: Brevo template ID.
            params: Template variable substitutions.
            sender: Dict with 'name' and 'email' keys. Falls back to account defaults.
            attachments: List of dicts with 'name' and either 'url' or 'content' (base64).
        """
        resolved_sender = sender or {}
        sender_email = resolved_sender.get("email") or self.account.default_sender_email
        sender_name = resolved_sender.get("name") or self.account.default_sender_name

        if not sender_email:
            raise BrevoAPIError("No sender email configured for this Brevo account.")

        payload: dict = {
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": to_email, "name": to_name or to_email}],
            "templateId": template_id,
        }
        if params:
            payload["params"] = params
        if attachments:
            payload["attachment"] = attachments

        result = self._client.request("POST", "/smtp/email", json=payload)
        return result or {}
