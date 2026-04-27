from django.urls import path
from apps.tenants.views import TenantListCreateView, TenantDetailView

urlpatterns = [
    path("", TenantListCreateView.as_view(), name="tenant-list-create"),
    path("<slug:slug>/", TenantDetailView.as_view(), name="tenant-detail"),
]
