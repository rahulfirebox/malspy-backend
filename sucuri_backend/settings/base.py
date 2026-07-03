import os
from datetime import timedelta
from pathlib import Path

import sentry_sdk
from celery.schedules import crontab
from corsheaders.defaults import default_headers
from decouple import config
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.redis import RedisIntegration

BASE_DIR = Path(__file__).resolve().parent.parent.parent

_REQUIRED_ENV_VARS = [
    "SECRET_KEY",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_HOST",
    "REDIS_URL",
    "AGENT_JWT_SIGNING_KEY",
    "ADMIN_URL",
    "EMAIL_HOST_PASSWORD",
]
_missing = [v for v in _REQUIRED_ENV_VARS if not os.environ.get(v) and not config(v, default=None)]
if _missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(_missing)}")

SECRET_KEY = config("SECRET_KEY")

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

DEBUG = config("DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django_prometheus",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_celery_beat",
    "apps.core",
    "apps.accounts.apps.AccountsConfig",
    "apps.scans",
    "apps.domains",
    "apps.alerts",
    "apps.billing",
    "apps.api_keys",
    "apps.agents",
    "drf_spectacular",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "apps.core.logging_filters.TraceIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "sucuri_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "sucuri_backend.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME"),
        "USER": config("DB_USER"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST"),
        "PORT": config("DB_PORT", default="5432"),
        "ATOMIC_REQUESTS": True,
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "connect_timeout": 10,
            "options": "-c statement_timeout=10000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=60000",
        },
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
USE_I18N = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ADMIN_URL = config("ADMIN_URL", default=None)
if not ADMIN_URL:
    raise RuntimeError("ADMIN_URL must be set in environment")

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 86400
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
X_FRAME_OPTIONS = "DENY"

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "apps.api_keys.authentication.ApiKeyAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    "DATETIME_FORMAT": "iso-8601",
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardCursorPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "apps.core.throttling.StandardUserThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "public_scan": "5/hour",
        "login": "5/minute",
        "sensitive": "3/hour",
        "user": "300/hour",
        "agent": "60/hour",
        "agent_auth": "5/minute",
        "registration": "10/hour",
        "password_reset": "3/hour",
        "email_verify": "10/hour",
        "scan_status_user": "60/minute",
        "scan_status_anon": "10/minute",
    },
    "NUM_PROXIES": 1,
}

AGENT_JWT_SIGNING_KEY = config("AGENT_JWT_SIGNING_KEY", default=config("SECRET_KEY"))

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "rest_framework_simplejwt.serializers.TokenObtainPairSerializer",
    "TOKEN_REFRESH_SERIALIZER": "rest_framework_simplejwt.serializers.TokenRefreshSerializer",
}

CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="http://localhost:3000").split(",")
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = list(default_headers) + [
    "idempotency-key",
    "x-request-id",
    "x-org-id",
    "x-trace-id",
]


REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://localhost:6379/1"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "sucuri",
    }
}


CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000
CELERY_TASK_REJECT_ON_WORKER_LOST = True


CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {
    "reset-monthly-quota": {
        "task": "apps.scans.tasks.reset_monthly_quota",
        "schedule": crontab(hour=0, minute=0),
    },
    "update-malware-signatures": {
        "task": "apps.scans.tasks.update_malware_signatures",
        "schedule": crontab(hour=2, minute=0),
    },
    "check-agent-health": {
        "task": "apps.agents.tasks.check_agent_health",
        "schedule": crontab(minute="*/5"),
    },
    "check-tls-expiry": {
        "task": "apps.domains.tasks.check_tls_expiry",
        "schedule": crontab(hour=3, minute=0),
    },
    "send-quota-warning-email": {
        "task": "apps.scans.tasks.send_quota_warning_email",
        "schedule": crontab(hour=8, minute=0),
    },
    "purge-expired-data": {
        "task": "apps.core.tasks.purge_expired_data",
        "schedule": crontab(hour=3, minute=0),
    },
    "cleanup-stale-scans": {
        "task": "apps.scans.tasks.cleanup_stale_scans",
        "schedule": crontab(hour=4, minute=0),
    },
    "trigger-scheduled-scans": {
        "task": "apps.domains.tasks.dispatch_scheduled_scans",
        "schedule": crontab(minute="*/5"),
    },
    "check-plan-expiry": {
        "task": "apps.billing.tasks.check_plan_expiry",
        "schedule": crontab(hour=1, minute=0),
    },
    "reconcile-financial-records": {
        "task": "apps.billing.tasks.reconcile_financial_records",
        "schedule": crontab(hour=3, minute=30),
        "options": {"expires": 3600},
    },
}


EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@sucuriclone.com")

FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3000")


MALICIOUS_DOMAINS = [
    "coinhive.com",
    "cryptoloot.pro",
    "webminepool.com",
    "googletagmanager.ru",
    "googleanalytics.ru",
    "steal-data.com",
    "malware-cdn.net",
    "c2-server.xyz",
    "phishing-domain.com",
]


SUCURI_API_URL = "https://sitecheck.sucuri.net/api/v3/"
SUCURI_API_TIMEOUT = 30


STRIPE_SECRET_KEY = config("STRIPE_SECRET_KEY", default="")
STRIPE_WEBHOOK_SECRET = config("STRIPE_WEBHOOK_SECRET", default="")


CASHFREE_APP_ID = config("CASHFREE_APP_ID", default="")
CASHFREE_SECRET_KEY = config("CASHFREE_SECRET_KEY", default="")
CASHFREE_ENVIRONMENT = config("CASHFREE_ENVIRONMENT")


PAYMENT_GATEWAY = config("PAYMENT_GATEWAY", default="cashfree")


SCAN_CACHE_TTL_PUBLIC = 86400
SCAN_CACHE_TTL_FREE = 604800
SCAN_CACHE_TTL_PRO = 2592000

DATA_RETENTION_DAYS = config("DATA_RETENTION_DAYS", default=90, cast=int)

SUPERADMIN_ENABLED = config("SUPERADMIN_ENABLED", default=False, cast=bool)

SENTRY_DSN = config("SENTRY_DSN", default="")
if SENTRY_DSN:

    def _before_send(event, hint):
        if "exc_info" in hint:
            exc_type, exc_value, tb = hint["exc_info"]
            from django.core.exceptions import ValidationError as DjValidationError
            from rest_framework.exceptions import (
                NotAuthenticated,
                PermissionDenied,
                ValidationError,
            )

            if isinstance(
                exc_value,
                (
                    ValidationError,
                    NotAuthenticated,
                    PermissionDenied,
                    DjValidationError,
                ),
            ):
                return None
        return event

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration(), RedisIntegration()],
        traces_sample_rate=float(config("SENTRY_TRACES_SAMPLE_RATE", default="0.1")),
        send_default_pii=False,
        before_send=_before_send,
        environment=config("DJANGO_ENV", default="production"),
    )
