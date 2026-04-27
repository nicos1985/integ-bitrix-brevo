import logging

from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.transactional.serializers import TransactionalSendSerializer
from apps.transactional.models import TransactionalEmailLog
from apps.brevo.transactional import BrevoTransactionalService
from apps.brevo.clients import BrevoAPIError
from apps.sync.models import SyncedContact

logger = logging.getLogger(__name__)


class TransactionalSendView(APIView):
    """
    POST /api/transactional/send/
    Manually trigger a transactional email send.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = TransactionalSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        tenant = data["tenant_slug"]
        brevo_account = tenant.brevo_accounts.filter(is_active=True).first()
        if not brevo_account:
            return Response(
                {"detail": "No active Brevo account for this tenant."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sender = data.get("sender") or {}
        to_email = data["to_email"]
        to_name = data.get("to_name") or None
        template_id = data["template_id"]
        params = data.get("params") or {}
        attachments = data.get("attachments") or []

        log = TransactionalEmailLog.objects.create(
            tenant=tenant,
            brevo_account=brevo_account,
            template_id=template_id,
            to_email=to_email,
            to_name=to_name,
            sender_email=sender.get("email") or "",
            sender_name=sender.get("name") or "",
            params=params,
            attachments=attachments,
            status=TransactionalEmailLog.STATUS_QUEUED,
        )

        try:
            contact = SyncedContact.objects.get(tenant=tenant, email=to_email.lower())
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
                params=params or None,
                sender=sender or None,
                attachments=attachments or None,
            )
            log.brevo_message_id = result.get("messageId") or result.get("message-id")
            log.status = TransactionalEmailLog.STATUS_SENT
            log.save(update_fields=["brevo_message_id", "status", "updated_at"])
            return Response({"status": "sent", "message_id": log.brevo_message_id})

        except BrevoAPIError as exc:
            log.status = TransactionalEmailLog.STATUS_ERROR
            log.error_message = str(exc)
            log.save(update_fields=["status", "error_message", "updated_at"])
            return Response({"status": "error", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
