import os

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from .base import *

DEBUG = True

ALLOWED_HOSTS = ["*"]

CASHFREE_ENVIRONMENT = "sandbox"


EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8080",
]


INTERNAL_IPS = ["127.0.0.1"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "trace_context": {
            "()": "apps.core.logging_filters.TraceContextFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} trace={otelTraceID} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["trace_context"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

from apps.core.telemetry import configure_opentelemetry

configure_opentelemetry(
    service_name="sucuri-backend",
    otlp_endpoint=os.environ.get("OTLP_ENDPOINT", ""),
)


_dev_dsn = os.environ.get("SENTRY_DSN", "")
if _dev_dsn:
    sentry_sdk.init(
        dsn=_dev_dsn,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0,
        environment="development",
    )
