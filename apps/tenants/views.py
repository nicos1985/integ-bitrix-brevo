from rest_framework import generics, permissions
from apps.tenants.models import Tenant
from apps.tenants.serializers import TenantSerializer


class TenantListCreateView(generics.ListCreateAPIView):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = [permissions.IsAdminUser]


class TenantDetailView(generics.RetrieveUpdateAPIView):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = [permissions.IsAdminUser]
    lookup_field = "slug"
