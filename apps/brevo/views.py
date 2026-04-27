import logging

from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.brevo.models import BrevoAccount
from apps.brevo.serializers import BrevoAccountCreateSerializer, BrevoAccountReadSerializer
from apps.brevo.clients import BrevoAPIError
from apps.brevo.transactional import BrevoTransactionalService

logger = logging.getLogger(__name__)


class BrevoAccountListCreateView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        accounts = BrevoAccount.objects.select_related("tenant").all()
        return Response(BrevoAccountReadSerializer(accounts, many=True).data)

    def post(self, request):
        serializer = BrevoAccountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = serializer.save()
        return Response(BrevoAccountReadSerializer(account).data, status=status.HTTP_201_CREATED)


class BrevoAccountDetailView(APIView):
    permission_classes = [IsAdminUser]

    def _get_account(self, pk):
        try:
            return BrevoAccount.objects.get(pk=pk)
        except BrevoAccount.DoesNotExist:
            return None

    def get(self, request, pk):
        account = self._get_account(pk)
        if not account:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(BrevoAccountReadSerializer(account).data)


class BrevoAccountTestView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        try:
            account = BrevoAccount.objects.get(pk=pk)
        except BrevoAccount.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            service = BrevoTransactionalService(account)
            templates = service.list_templates()
            return Response({"status": "ok", "template_count": len(templates)})
        except BrevoAPIError as exc:
            return Response({"status": "error", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class BrevoTemplateListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        try:
            account = BrevoAccount.objects.get(pk=pk)
        except BrevoAccount.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            service = BrevoTransactionalService(account)
            templates = service.list_templates()
            return Response(templates)
        except BrevoAPIError as exc:
            return Response({"status": "error", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
