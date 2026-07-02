from django.conf import settings
from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path


def health_live(request):
    return JsonResponse({"success": True, "data": {"status": "ok"}})


def health_ready(request):
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({"success": False, "data": {"status": "db_unavailable"}}, status=503)
    try:

        cache.get("__health__")
    except Exception:
        return JsonResponse({"success": False, "data": {"status": "cache_unavailable"}}, status=503)
    return JsonResponse({"success": True, "data": {"status": "ok"}})


urlpatterns = [
    path("", include("django_prometheus.urls")),
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/v1/health/live/", health_live),
    path("api/v1/health/ready/", health_ready),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/org/", include("apps.accounts.org_urls")),
    path("api/v1/", include("apps.scans.urls")),
    path("api/v1/agents/", include("apps.agents.urls")),
    path("api/v1/agent/", include("apps.agents.agent_urls")),
    path("api/v1/domains/", include("apps.domains.urls")),
    path("api/v1/alerts/", include("apps.alerts.urls")),
    path("api/v1/billing/", include("apps.billing.urls")),
    path("api/v1/api-keys/", include("apps.api_keys.urls")),
    path("api/v1/scan/analytics/", include("apps.scans.analytics_urls")),
]

if settings.SUPERADMIN_ENABLED:
    urlpatterns += [
        path("api/v1/superadmin/", include("apps.superadmin.urls")),
    ]

if settings.DEBUG:
    from drf_spectacular.views import SpectacularAPIView

    _docs_url = getattr(settings, "API_DOCS_URL", "internal-docs-api/")
    urlpatterns += [path(f"{_docs_url}", SpectacularAPIView.as_view(), name="schema")]
