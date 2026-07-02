import logging

import sentry_sdk

try:
    import redis as _redis_module

    _REDIS_CONNECTION_ERROR = _redis_module.exceptions.ConnectionError
except ImportError:
    _REDIS_CONNECTION_ERROR = None
from rest_framework.exceptions import APIException, NotFound, Throttled
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class ResourceNotFound(NotFound):

    def __init__(self, detail=None):
        super().__init__(detail=detail or "Resource not found.")


class QuotaExceededException(APIException):

    status_code = 402
    default_code = "BILLING_QUOTA_EXCEEDED"

    def __init__(self, detail=None, code=None):
        super().__init__(detail or "Quota exceeded. Upgrade your plan.", code)


HTTP_CODE_MAP = {
    400: "VALIDATION_ERROR",
    401: "AUTHENTICATION_REQUIRED",
    402: "QUOTA_EXCEEDED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    429: "RATE_LIMIT_EXCEEDED",
    500: "SERVER_ERROR",
}


def custom_exception_handler(exc, context):
    if _REDIS_CONNECTION_ERROR and isinstance(exc, _REDIS_CONNECTION_ERROR):
        logger.error("Redis connection error", exc_info=True, extra={})
        return Response(
            {
                "success": False,
                "error": {
                    "error_code": "SERVICE_UNAVAILABLE",
                    "message": "Service temporarily unavailable.",
                },
            },
            status=503,
        )

    response = exception_handler(exc, context)

    if response is None:
        logger.error("Unhandled exception: %s", exc, exc_info=True, extra={})
        sentry_sdk.capture_exception(exc)
        return Response(
            {
                "success": False,
                "error": {
                    "error_code": "SERVER_ERROR",
                    "message": "An unexpected error occurred.",
                },
            },
            status=500,
        )

    if response.status_code >= 500:
        sentry_sdk.capture_exception(exc)

    error_data = response.data
    error_code = HTTP_CODE_MAP.get(response.status_code, "SERVER_ERROR")
    message = "An error occurred."
    errors = None

    if isinstance(error_data, dict):
        if "detail" in error_data:
            raw = error_data["detail"]
            message = str(raw) if raw else message
        elif "code" in error_data and "detail" in error_data:
            error_code = str(error_data.get("code", error_code))
            message = str(error_data.get("detail", message))
        else:
            message = "Validation failed."
            errors = {
                field: [str(e) for e in errs] if isinstance(errs, list) else [str(errs)]
                for field, errs in error_data.items()
            }
    elif isinstance(error_data, list):
        message = "; ".join(str(e) for e in error_data)
    else:
        message = str(error_data)

    if isinstance(exc, Throttled) and exc.wait is not None:
        response["Retry-After"] = str(int(exc.wait))

    payload = {
        "success": False,
        "error": {
            "error_code": error_code,
            "message": message,
        },
    }
    if errors:
        payload["error"]["errors"] = errors

    response.data = payload
    return response


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")
