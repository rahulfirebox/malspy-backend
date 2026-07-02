import logging

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def health_live(request):
    return JsonResponse({"status": "ok"})


def health_ready(request):
    checks = {"db": False, "redis": False}
    try:
        connection.ensure_connection()
        checks["db"] = True
    except Exception as exc:
        logger.warning("health_ready: DB check failed: %s", exc, extra={"check": "db"})
    _HEALTH_PROBE_KEY = "__health__"
    try:
        cache.set(_HEALTH_PROBE_KEY, "1", 10)
        checks["redis"] = cache.get(_HEALTH_PROBE_KEY) == "1"
    except Exception as exc:
        logger.warning("health_ready: Redis check failed: %s", exc, extra={"check": "redis"})
    ok = all(checks.values())
    return JsonResponse(
        {"status": "ok" if ok else "degraded", "checks": checks},
        status=200 if ok else 503,
    )
