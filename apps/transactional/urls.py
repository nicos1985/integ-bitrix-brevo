from django.urls import path
from apps.transactional.views import TransactionalSendView

urlpatterns = [
    path("send/", TransactionalSendView.as_view(), name="transactional-send"),
]
