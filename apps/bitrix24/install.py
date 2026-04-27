import logging
from datetime import datetime, timezone

from django.conf import settings

from apps.core.encryption import encrypt_value
from apps.sync.models import SyncLog

logger = logging.getLogger(__name__)


def handle_install(payload: dict) -> dict:
    """
    Process the Bitrix24 install payload.

    Bitrix24 POSTs to the install handler with the following fields:
      DOMAIN, member_id, AUTH_ID (access_token), REFRESH_ID (refresh_token),
      APP_SID (application token), AUTH_EXPIRES, access_token, refresh_token, etc.

    Returns a dict with {'status': 'ok'} or raises on error.
    """
    from apps.tenants.models import Tenant
    from apps.bitrix24.models import BitrixPortal
    from apps.bitrix24.clients import BitrixClient

    domain = (payload.get("DOMAIN") or payload.get("domain") or "").strip().lower()
    member_id = payload.get("member_id") or payload.get("MEMBER_ID") or ""
    access_token = payload.get("AUTH_ID") or payload.get("access_token") or ""
    refresh_token = payload.get("REFRESH_ID") or payload.get("refresh_token") or ""
    application_token = payload.get("APP_SID") or payload.get("application_token") or ""
    rest_endpoint = payload.get("PROTOCOL", "https") + "://" + domain + "/rest" if domain else ""
    auth_expires = payload.get("AUTH_EXPIRES") or 3600

    if not domain:
        raise ValueError("Missing DOMAIN in install payload.")

    # Derive tenant slug from domain, e.g. "cliente.bitrix24.com" → "cliente-bitrix24-com"
    tenant_slug = domain.replace(".", "-")
    tenant, _ = Tenant.objects.get_or_create(
        slug=tenant_slug,
        defaults={"name": domain, "is_active": True},
    )

    client_id = settings.BITRIX_APP_CLIENT_ID
    client_secret = settings.BITRIX_APP_CLIENT_SECRET

    portal, _ = BitrixPortal.objects.update_or_create(
        domain=domain,
        defaults={
            "tenant": tenant,
            "member_id": member_id or None,
            "client_id": client_id,
            "client_secret_encrypted": encrypt_value(client_secret),
            "access_token_encrypted": encrypt_value(access_token),
            "refresh_token_encrypted": encrypt_value(refresh_token),
            "application_token": application_token or None,
            "rest_endpoint": rest_endpoint or None,
            "installed_at": datetime.now(tz=timezone.utc),
            "uninstalled_at": None,
            "is_active": True,
        },
    )

    # Register events and bizproc activity
    if access_token:
        try:
            _register_handlers(portal)
        except Exception as exc:
            logger.error("Failed to register handlers for %s: %s", domain, exc)

    SyncLog.objects.create(
        tenant=tenant,
        source=SyncLog.SOURCE_SYSTEM,
        direction=SyncLog.DIRECTION_INSTALL,
        event_type="app_install",
        status=SyncLog.STATUS_SUCCESS,
        message=f"App installed on {domain}",
        request_payload={"domain": domain, "member_id": member_id},
    )

    logger.info("App installed successfully on portal %s", domain)
    return {"status": "ok", "portal_id": portal.pk}


def handle_uninstall(payload: dict) -> dict:
    """Mark portal as uninstalled."""
    from apps.bitrix24.models import BitrixPortal

    domain = (payload.get("DOMAIN") or payload.get("domain") or "").strip().lower()
    member_id = payload.get("member_id") or payload.get("MEMBER_ID") or ""

    qs = BitrixPortal.objects.all()
    if domain:
        qs = qs.filter(domain=domain)
    elif member_id:
        qs = qs.filter(member_id=member_id)

    updated = qs.update(is_active=False, uninstalled_at=datetime.now(tz=timezone.utc))
    logger.info("Portal(s) marked as uninstalled: domain=%s, count=%s", domain, updated)
    return {"status": "ok"}


def _register_handlers(portal) -> None:
    """Register Bitrix24 event handlers and bizproc activity for a portal."""
    from apps.bitrix24.clients import BitrixClient

    base_url = settings.BITRIX_APP_BASE_URL.rstrip("/")
    client = BitrixClient(portal)

    # Event handlers
    for event_name, path in [
        ("onCrmContactAdd", "/api/bitrix/events/contact-add/"),
        ("onCrmContactUpdate", "/api/bitrix/events/contact-update/"),
        ("onAppUninstall", "/api/bitrix/events/app-uninstall/"),
    ]:
        try:
            client.register_event(event_name, f"{base_url}{path}")
            logger.info("Registered event %s for portal %s", event_name, portal.domain)
        except Exception as exc:
            logger.warning("Could not register event %s for %s: %s", event_name, portal.domain, exc)

    # Bizproc activity
    try:
        from apps.bitrix24.workflows import WorkflowService
        WorkflowService(portal).register_brevo_send_email_activity()
    except Exception as exc:
        logger.warning("Could not register bizproc activity for %s: %s", portal.domain, exc)
