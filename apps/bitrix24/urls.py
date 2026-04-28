from django.urls import path
from apps.bitrix24.views import (
    BitrixInstallView,
    BitrixPortalRegisterView,
    BitrixContactAddEventView,
    BitrixContactUpdateEventView,
    BitrixAppUninstallEventView,
    BitrixWorkflowSendEmailView,
    BitrixWorkflowConfigView,
)

urlpatterns = [
    path("portals/", BitrixPortalRegisterView.as_view(), name="bitrix-portal-register"),
    path("install/", BitrixInstallView.as_view(), name="bitrix-install"),
    path("events/contact-add/", BitrixContactAddEventView.as_view(), name="bitrix-contact-add"),
    path("events/contact-update/", BitrixContactUpdateEventView.as_view(), name="bitrix-contact-update"),
    path("events/app-uninstall/", BitrixAppUninstallEventView.as_view(), name="bitrix-app-uninstall"),
    path("workflows/brevo-send-email/", BitrixWorkflowSendEmailView.as_view(), name="bitrix-workflow-send-email"),
    path("workflows/brevo-config/", BitrixWorkflowConfigView.as_view(), name="bitrix-workflow-config"),
]
