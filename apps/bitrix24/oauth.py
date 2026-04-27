import logging
import time
from datetime import datetime, timezone

import requests
from django.conf import settings

from apps.core.encryption import decrypt_value, encrypt_value

logger = logging.getLogger(__name__)

BITRIX_OAUTH_URL = "https://oauth.bitrix.info/oauth/token/"


class BitrixOAuthError(Exception):
    pass


class BitrixOAuthService:
    """Handles OAuth token refresh for a BitrixPortal instance."""

    def refresh_access_token(self, portal) -> None:
        """
        Refresh the access token using the stored refresh token.
        Updates the portal record in place and saves to DB.
        Raises BitrixOAuthError on non-recoverable failures.
        """
        from apps.bitrix24.models import BitrixPortal  # local import avoids circular

        client_id = portal.client_id
        client_secret = decrypt_value(portal.client_secret_encrypted)
        refresh_token = decrypt_value(portal.refresh_token_encrypted)

        if not refresh_token:
            raise BitrixOAuthError(f"Portal {portal.domain} has no refresh token stored.")

        params = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        }

        for attempt in range(3):
            try:
                resp = requests.get(BITRIX_OAUTH_URL, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                break
            except requests.Timeout:
                if attempt == 2:
                    raise BitrixOAuthError("Timeout refreshing Bitrix token after 3 attempts.")
                time.sleep(2 ** attempt)
            except requests.HTTPError as exc:
                raise BitrixOAuthError(f"HTTP error refreshing token: {exc}") from exc

        if "error" in data:
            raise BitrixOAuthError(f"Bitrix OAuth error: {data.get('error')} — {data.get('error_description')}")

        portal.access_token_encrypted = encrypt_value(data["access_token"])
        portal.refresh_token_encrypted = encrypt_value(data["refresh_token"])

        expires_in = int(data.get("expires_in", 3600))
        portal.token_expires_at = datetime.fromtimestamp(
            time.time() + expires_in, tz=timezone.utc
        )
        portal.save(update_fields=["access_token_encrypted", "refresh_token_encrypted", "token_expires_at", "updated_at"])

        logger.info("Refreshed access token for portal %s", portal.domain)
