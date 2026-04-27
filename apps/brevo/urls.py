from django.urls import path
from apps.brevo.views import (
    BrevoAccountListCreateView,
    BrevoAccountDetailView,
    BrevoAccountTestView,
    BrevoTemplateListView,
)
from apps.brevo.webhooks import BrevoMarketingWebhookView, BrevoTransactionalWebhookView

urlpatterns = [
    path("accounts/", BrevoAccountListCreateView.as_view(), name="brevo-account-list-create"),
    path("accounts/<int:pk>/", BrevoAccountDetailView.as_view(), name="brevo-account-detail"),
    path("accounts/<int:pk>/test/", BrevoAccountTestView.as_view(), name="brevo-account-test"),
    path("accounts/<int:pk>/templates/", BrevoTemplateListView.as_view(), name="brevo-template-list"),
    path("webhooks/marketing/", BrevoMarketingWebhookView.as_view(), name="brevo-webhook-marketing"),
    path("webhooks/transactional/", BrevoTransactionalWebhookView.as_view(), name="brevo-webhook-transactional"),
]
