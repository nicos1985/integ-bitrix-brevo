import logging
import time

import requests

from apps.core.encryption import decrypt_value

logger = logging.getLogger(__name__)

BREVO_BASE_URL = "https://api.brevo.com/v3"


class BrevoAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class BrevoClient:
    """Low-level HTTP client for the Brevo v3 API."""

    def __init__(self, account):
        self.account = account

    def _get_api_key(self) -> str:
        return decrypt_value(self.account.api_key_encrypted) or ""

    def request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict | None:
        """
        Execute an HTTP request against the Brevo API.
        Returns parsed JSON or None for 204 responses.
        Raises BrevoAPIError on failure.
        """
        url = f"{BREVO_BASE_URL}/{path.lstrip('/')}"
        headers = {
            "api-key": self._get_api_key(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        for attempt in range(3):
            try:
                resp = requests.request(
                    method.upper(),
                    url,
                    headers=headers,
                    json=json,
                    params=params,
                    timeout=20,
                )
            except requests.Timeout:
                if attempt == 2:
                    raise BrevoAPIError(f"Timeout calling Brevo {method} {path} after 3 attempts.")
                time.sleep(2 ** attempt)
                continue

            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 2 ** (attempt + 1)))
                logger.warning("Brevo rate limit hit. Waiting %s seconds.", retry_after)
                time.sleep(retry_after)
                continue

            if resp.status_code == 204:
                return None

            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                try:
                    error_body = resp.json()
                    msg = error_body.get("message", str(exc))
                except Exception:
                    msg = str(exc)
                raise BrevoAPIError(
                    f"Brevo HTTP {resp.status_code} {method} {path}: {msg}",
                    status_code=resp.status_code,
                ) from exc

            return resp.json()

        raise BrevoAPIError(f"Failed Brevo {method} {path} after 3 attempts.")
