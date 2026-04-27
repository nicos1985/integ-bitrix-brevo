from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/tenants/", include("apps.tenants.urls")),
    path("api/bitrix/", include("apps.bitrix24.urls")),
    path("api/brevo/", include("apps.brevo.urls")),
    path("api/sync/", include("apps.sync.urls")),
    path("api/transactional/", include("apps.transactional.urls")),
]
