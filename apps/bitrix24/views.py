import logging

from rest_framework import serializers
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bitrix24.install import handle_install, handle_uninstall
from apps.bitrix24.models import BitrixPortal
from apps.bitrix24.workflows import WorkflowService
from apps.core.encryption import encrypt_value
from apps.sync.services import SyncService
from apps.sync.models import SyncLog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serializer for portal pre-registration
# ---------------------------------------------------------------------------

class BitrixPortalRegisterSerializer(serializers.Serializer):
    tenant_slug = serializers.SlugField()
    domain = serializers.CharField(max_length=255)
    client_id = serializers.CharField(max_length=255)
    client_secret = serializers.CharField(max_length=255, write_only=True)

    def validate_tenant_slug(self, value):
        from apps.tenants.models import Tenant
        try:
            return Tenant.objects.get(slug=value)
        except Tenant.DoesNotExist:
            raise serializers.ValidationError(f"Tenant '{value}' not found.")

    def validate_domain(self, value):
        return value.strip().lower()


class BitrixPortalRegisterView(APIView):
    """
    POST /api/bitrix/portals/

    Pre-register a Bitrix24 portal before the OAuth install flow.
    The client_id and client_secret come from the portal's Developer Resources.
    Must be called before pointing the install URL to /api/bitrix/install/.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = BitrixPortalRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        tenant = data["tenant_slug"]
        domain = data["domain"]

        portal, created = BitrixPortal.objects.update_or_create(
            domain=domain,
            defaults={
                "tenant": tenant,
                "client_id": data["client_id"],
                "client_secret_encrypted": encrypt_value(data["client_secret"]),
                "is_active": True,
            },
        )
        return Response(
            {
                "id": portal.pk,
                "domain": portal.domain,
                "tenant": tenant.slug,
                "client_id": portal.client_id,
                "created": created,
                "install_url": f"/api/bitrix/install/",
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


def _get_portal(payload: dict):
    """
    Resolve a BitrixPortal from event payload.
    Bitrix24 sends auth data as flat bracket-notation keys:
      auth[member_id], auth[domain]
    or nested dict (auth.member_id) depending on the client used.
    """
    def _v(key, *fallbacks):
        for k in (key, *fallbacks):
            v = payload.get(k)
            if v:
                return (v[0] if isinstance(v, list) else v).strip()
        return ""

    member_id = _v("auth[member_id]", "member_id") or (
        payload.get("auth", {}).get("member_id", "") if isinstance(payload.get("auth"), dict) else ""
    )
    domain = _v("auth[domain]", "DOMAIN", "domain") or (
        payload.get("auth", {}).get("domain", "") if isinstance(payload.get("auth"), dict) else ""
    )
    domain = domain.lower()

    if member_id:
        portal = BitrixPortal.objects.filter(member_id=member_id, is_active=True).first()
        if portal:
            return portal
    if domain:
        return BitrixPortal.objects.filter(domain=domain, is_active=True).first()
    return None


class BitrixInstallView(APIView):
    """
    GET/POST /api/bitrix/install/
    Called by Bitrix24 during app installation.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return self._process(request)

    def post(self, request):
        return self._process(request)

    def _process(self, request):
        payload = {**request.data, **request.query_params.dict()}
        logger.info("Bitrix install payload received: %s", payload)
        try:
            result = handle_install(payload)
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            logger.warning("Bitrix install rejected: %s | payload: %s", exc, payload)
            return Response({"status": "error", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.error("Install handler error: %s | payload: %s", exc, payload)
            return Response({"status": "error", "detail": "Internal error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BitrixContactAddEventView(APIView):
    """
    POST /api/bitrix/events/contact-add/
    Handles onCrmContactAdd events from Bitrix24.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        logger.info("contact-add payload received: %s", payload)
        portal = _get_portal(payload)
        if not portal:
            logger.warning("Bitrix contact-add: portal not found. payload keys: %s", list(payload.keys()))
            return Response({"status": "ok"})  # Return 200 so Bitrix doesn't retry indefinitely

        logger.info("contact-add: portal found: %s", portal.domain)
        brevo_account = portal.tenant.brevo_accounts.filter(is_active=True).first()  # type: ignore[attr-defined]
        if not brevo_account:
            logger.warning("contact-add: No active Brevo account for tenant %s", portal.tenant)
            return Response({"status": "ok"})
            logger.warning("No active Brevo account for tenant %s", portal.tenant)
            return Response({"status": "ok"})

        try:
            svc = SyncService(portal, brevo_account)
            svc.sync_from_bitrix_event("onCrmContactAdd", payload)
        except Exception as exc:
            logger.error("Error handling onCrmContactAdd: %s", exc)

        return Response({"status": "ok"})


class BitrixContactUpdateEventView(APIView):
    """
    POST /api/bitrix/events/contact-update/
    Handles onCrmContactUpdate events from Bitrix24.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        portal = _get_portal(payload)
        if not portal:
            logger.warning("Bitrix contact-update: portal not found.")
            return Response({"status": "ok"})

        brevo_account = portal.tenant.brevo_accounts.filter(is_active=True).first()  # type: ignore[attr-defined]
        if not brevo_account:
            return Response({"status": "ok"})

        try:
            svc = SyncService(portal, brevo_account)
            svc.sync_from_bitrix_event("onCrmContactUpdate", payload)
        except Exception as exc:
            logger.error("Error handling onCrmContactUpdate: %s", exc)

        return Response({"status": "ok"})


class BitrixAppUninstallEventView(APIView):
    """
    POST /api/bitrix/events/app-uninstall/
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        try:
            handle_uninstall(payload)
        except Exception as exc:
            logger.error("Error handling app-uninstall: %s", exc)
        return Response({"status": "ok"})


class BitrixWorkflowSendEmailView(APIView):
    """
    POST /api/bitrix/workflows/brevo-send-email/
    Called by Bitrix24 when a bizproc workflow node is executed.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        logger.info("Workflow brevo-send-email payload: %s", payload)
        portal = _get_portal(payload)
        if not portal:
            logger.warning("Workflow brevo-send-email: portal not found.")
            return Response({"status": "error", "message": "Portal not found."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            svc = WorkflowService(portal)
            result = svc.handle_brevo_send_email_activity(payload)
            return Response(result)
        except Exception as exc:
            logger.error("Error in workflow brevo-send-email: %s", exc)
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BitrixWorkflowConfigView(APIView):
    """
    GET /api/bitrix/workflows/brevo-config/
    Returns list of available Brevo templates for workflow configuration.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        from apps.brevo.models import BrevoAccount
        from apps.brevo.transactional import BrevoTransactionalService
        from apps.brevo.clients import BrevoAPIError

        portal = _get_portal(request.query_params.dict())
        tenant = portal.tenant if portal else None
        if not tenant:
            return Response({"templates": []})

        account = tenant.brevo_accounts.filter(is_active=True).first()  # type: ignore[attr-defined]
        if not account:
            return Response({"templates": []})

        try:
            templates = BrevoTransactionalService(account).list_templates()
            return Response({"templates": templates})
        except BrevoAPIError as exc:
            return Response({"templates": [], "error": str(exc)})
