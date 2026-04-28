import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.brevo.models import BrevoAccount
from apps.sync.services import SyncService

logger = logging.getLogger(__name__)


class BrevoMarketingWebhookView(APIView):
    """
    POST /api/brevo/webhooks/marketing/?secret=<secret>
    Receives marketing events from Brevo.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        secret = request.query_params.get("secret", "")
        payload = request.data if isinstance(request.data, dict) else {}

        account = self._resolve_account(secret)
        if not account:
            logger.warning("Brevo marketing webhook: invalid secret or no matching account.")
            return Response({"detail": "Unauthorized."}, status=status.HTTP_401_UNAUTHORIZED)

        event_type = payload.get("event") or payload.get("type") or ""
        logger.info("Brevo marketing webhook event=%s account=%s", event_type, account.pk)

        portal = (
            account.tenant.bitrix_portals.filter(is_active=True).first()  # type: ignore[attr-defined]
        )
        if not portal:
            logger.warning("No active Bitrix portal for tenant %s, skipping sync.", account.tenant)
            return Response({"status": "ok"})

        try:
            svc = SyncService(portal, account)
            svc.sync_from_brevo_webhook(event_type, payload)
        except Exception as exc:
            logger.error("Error handling Brevo marketing webhook: %s", exc)

        return Response({"status": "ok"})

    @staticmethod
    def _resolve_account(secret: str):
        if not secret:
            return None
        return BrevoAccount.objects.filter(webhook_secret=secret, is_active=True).first()


class BrevoTransactionalWebhookView(APIView):
    """
    POST /api/brevo/webhooks/transactional/?secret=<secret>
    Receives transactional events from Brevo (delivered, opened, bounce, etc.).
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        secret = request.query_params.get("secret", "")
        payload = request.data if isinstance(request.data, dict) else {}

        account = BrevoMarketingWebhookView._resolve_account(secret)
        if not account:
            logger.warning("Brevo transactional webhook: invalid secret.")
            return Response({"detail": "Unauthorized."}, status=status.HTTP_401_UNAUTHORIZED)

        event_type = payload.get("event") or payload.get("type") or ""
        logger.info("Brevo transactional webhook event=%s payload=%s", event_type, payload)

        portal = account.tenant.bitrix_portals.filter(is_active=True).first()  # type: ignore[attr-defined]
        if portal:
            try:
                svc = SyncService(portal, account)
                svc.sync_from_brevo_webhook(event_type, payload)
            except Exception as exc:
                logger.error("Error handling Brevo transactional webhook: %s", exc)

        return Response({"status": "ok"})
