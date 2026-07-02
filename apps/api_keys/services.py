import hashlib
import logging
import secrets

from django.db import IntegrityError, OperationalError, ProgrammingError, transaction
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.models import AuditLog

from .models import ApiKey

logger = logging.getLogger(__name__)

API_KEY_LIMIT = 10


def list_api_keys(org):
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    try:
        return (
            ApiKey.objects.filter(
                organization=org,
                deleted_at__isnull=True,
                revoked=False,
            )
            .select_related("organization", "created_by")
            .order_by("-created_at")
        )
    except (OperationalError, ProgrammingError) as e:
        logger.error("ApiKeyService.list DB error: %s", e, extra={"org_id": str(org.id)})
        raise ValidationError({"detail": "Database temporarily unavailable."})
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "ApiKeyService.list unexpected error: %s",
            e,
            exc_info=True,
            extra={"org_id": str(org.id)},
        )
        raise


def create_api_key(data: dict, org, user) -> tuple:
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    if org.plan is None or not org.plan.api_access:
        raise ValidationError(
            {
                "code": "PLAN_REQUIRED",
                "detail": "API key access requires Enterprise plan.",
            }
        )
    api_key = None
    raw_key = None
    for _attempt in range(3):
        try:
            _candidate = f"sk_live_{secrets.token_urlsafe(32)}"
            _key_hash = hashlib.sha256(_candidate.encode()).hexdigest()
            _key_prefix = _candidate[:8]
            with transaction.atomic():
                locked_org = type(org).objects.select_for_update().get(pk=org.pk)
                current_count = ApiKey.objects.filter(
                    organization=locked_org,
                    deleted_at__isnull=True,
                    revoked=False,
                ).count()
                if current_count >= API_KEY_LIMIT:
                    raise ValidationError(
                        {
                            "code": "API_KEY_LIMIT_REACHED",
                            "detail": "Maximum 10 API keys per organization.",
                        }
                    )
                api_key = ApiKey.objects.create(
                    organization=locked_org,
                    name=data["name"],
                    key_hash=_key_hash,
                    key_prefix=_key_prefix,
                    created_by=user,
                    expires_at=data.get("expires_at"),
                )
                try:
                    AuditLog.objects.create(
                        organization=locked_org,
                        actor=user,
                        action="API_KEY_CREATED",
                        resource_type="api_key",
                        resource_id=str(api_key.id),
                        changes={"name": data["name"], "key_prefix": _key_prefix},
                    )
                except Exception as exc:
                    logger.warning(
                        "ApiKeyService.create audit log failed: %s",
                        exc,
                        extra={"org_id": str(org.id), "key_prefix": _key_prefix},
                    )
            raw_key = _candidate
            break
        except IntegrityError:
            if _attempt == 2:
                raise ValidationError({"detail": "Unable to generate API key. Try again."})
        except ValidationError:
            raise
        except (OperationalError, ProgrammingError) as e:
            logger.error("ApiKeyService.create DB error: %s", e, extra={"org_id": str(org.id)})
            raise ValidationError({"detail": "Service unavailable."})
    return api_key, raw_key


def revoke_api_key(key_id: str, org, user) -> None:
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    with transaction.atomic():
        try:
            key = (
                ApiKey.objects.select_for_update()
                .filter(
                    organization=org,
                    deleted_at__isnull=True,
                )
                .get(pk=key_id)
            )
        except ApiKey.DoesNotExist:
            raise NotFound("API key not found.")
        except (OperationalError, ProgrammingError) as e:
            logger.error(
                "ApiKeyService.revoke DB error: %s",
                e,
                extra={"org_id": str(org.id), "key_id": str(key_id)},
            )
            raise ValidationError({"detail": "Service unavailable."})
        if key.revoked:
            return
        key.revoked = True
        key.save(update_fields=["revoked", "updated_at"])
        try:
            AuditLog.objects.create(
                organization=org,
                actor=user,
                action="API_KEY_REVOKED",
                resource_type="api_key",
                resource_id=str(key_id),
                changes={"key_prefix": key.key_prefix},
            )
        except ValidationError:
            raise
        except Exception as exc:
            logger.warning(
                "ApiKeyService.revoke audit log failed: %s",
                exc,
                extra={"org_id": str(org.id), "key_id": str(key_id)},
            )
