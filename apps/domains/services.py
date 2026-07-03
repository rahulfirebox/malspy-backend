import ipaddress
import logging
import socket

from django.db import IntegrityError, OperationalError, ProgrammingError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from .models import Domain

logger = logging.getLogger(__name__)


def _validate_domain_ssrf(domain_str: str) -> None:
    try:
        ip = socket.gethostbyname(domain_str)
        addr = ipaddress.ip_address(ip)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise ValidationError(
                {"domain": ["Domain resolves to a private or reserved IP address."]}
            )
    except socket.gaierror as exc:
        logger.debug(
            "_validate_domain_ssrf: DNS resolution failed for %s: %s",
            domain_str,
            exc,
            extra={"domain": domain_str},
        )


DOMAIN_ALLOWED_UPDATE_FIELDS = {
    "is_active",
    "frequency",
    "notify_email",
    "slack_webhook_url",
    "updated_at",
}


def list_domains(org, q=None, status=None):
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    try:
        qs = (
            Domain.objects.filter(
                organization=org,
                deleted_at__isnull=True,
            )
            .select_related("last_scan")
            .order_by("-created_at")
        )

        if q:
            qs = qs.filter(domain__icontains=q)
        valid_statuses = {"clean", "infected", "blacklisted", "unknown"}
        if status and status in valid_statuses:
            qs = qs.filter(last_status=status)

        return qs
    except (OperationalError, ProgrammingError) as e:
        logger.error(
            "DomainService.list DB error: %s",
            e,
            extra={"org_id": str(org.id) if org else None},
        )
        raise ValidationError({"detail": "Database temporarily unavailable."})
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "DomainService.list unexpected error: %s",
            e,
            exc_info=True,
            extra={"org_id": str(org.id) if org else None},
        )
        raise


def _domain_creation_error_from_integrity(domain_str: str, exc: IntegrityError) -> str:
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    constraint_name = None
    pgcode = None
    if cause is not None:
        diag = getattr(cause, "diag", None)
        if diag is not None:
            constraint_name = getattr(diag, "constraint_name", None)
        pgcode = getattr(cause, "pgcode", None)

    if constraint_name == "unique_active_domain_per_org" or pgcode == "23505":
        return f"Domain {domain_str} is already being monitored."
    if constraint_name == "domain_frequency_valid":
        return f"Invalid scan frequency for domain {domain_str}."
    if constraint_name == "domain_last_status_valid":
        return f"Invalid status for domain {domain_str}."
    if pgcode == "23503":
        return (
            f"Failed to create domain {domain_str}: organization or user reference is invalid."
        )
    if pgcode == "23514":
        return f"Failed to create domain {domain_str}: one or more field values are invalid."
    if pgcode == "23502":
        if "slack_webhook_url" in str(exc).lower():
            return f"Failed to create domain {domain_str}: slack webhook URL is required."
        return f"Failed to create domain {domain_str}: a required field is missing."

    logger.error(
        "create_domain IntegrityError for %s: %s (constraint=%s, pgcode=%s)",
        domain_str,
        exc,
        constraint_name,
        pgcode,
        exc_info=True,
        extra={"domain": domain_str, "constraint": constraint_name, "pgcode": pgcode},
    )
    return f"Failed to create domain {domain_str}. Please try again."


def create_domain(data: dict, org, user) -> Domain:
    if org is None:
        raise ValidationError({"detail": "Organization context required."})

    if not org.plan or org.plan.domain_quota == 0:
        raise ValidationError(
            {
                "code": "PLAN_REQUIRED",
                "detail": "Domain monitoring requires a paid plan.",
            }
        )

    domain_str = data["domain"]
    _validate_domain_ssrf(domain_str)
    try:
        with transaction.atomic():
            from apps.accounts.models import Organization

            org_locked = Organization.objects.select_for_update(of=("self",)).get(pk=org.pk)

            plan = org_locked.plan
            if plan is not None and plan.domain_quota != -1:
                current_count = Domain.objects.filter(
                    organization=org_locked,
                    deleted_at__isnull=True,
                    is_active=True,
                ).count()
                if current_count >= plan.domain_quota:
                    raise ValidationError(
                        {
                            "code": "QUOTA_EXCEEDED",
                            "detail": f"Domain quota exceeded. Your plan allows {plan.domain_quota} domains.",
                        }
                    )

            existing = (
                Domain.objects.select_for_update()
                .filter(
                    organization=org_locked,
                    domain=domain_str,
                    deleted_at__isnull=True,
                )
                .first()
            )
            if existing:
                raise ValidationError(
                    {"domain": [f"Domain {domain_str} is already being monitored."]}
                )

            domain = Domain.objects.create(
                organization=org_locked,
                domain=domain_str,
                frequency=data.get("frequency", "daily"),
                notify_email=data.get("notify_email", True),
                slack_webhook_url=data.get("slack_webhook_url") or "",
                created_by=user,
            )

            transaction.on_commit(lambda: _trigger_initial_scan(str(domain.id)))

    except IntegrityError as exc:
        domain = Domain.objects.filter(
            organization=org, domain=domain_str, deleted_at__isnull=True
        ).first()
        if domain is not None:
            raise ValidationError(
                {"domain": [f"Domain {domain_str} is already being monitored."]}
            )
        raise ValidationError(
            {"domain": [_domain_creation_error_from_integrity(domain_str, exc)]}
        )

    try:
        from apps.core.models import AuditLog

        AuditLog.objects.create(
            organization=org,
            actor=user,
            action="CREATE",
            resource_type="Domain",
            resource_id=str(domain.id),
            changes={"domain": domain_str, "frequency": domain.frequency},
        )
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "AuditLog create failed for domain %s: %s",
            domain.id,
            e,
            extra={"domain_id": str(domain.id)},
        )

    return domain


def _trigger_initial_scan(domain_id: str) -> None:
    try:
        from .tasks import trigger_scheduled_scan

        trigger_scheduled_scan.delay(domain_id)
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "Initial scan trigger failed for domain %s: %s",
            domain_id,
            e,
            extra={"domain_id": domain_id},
        )


def get_domain(domain_id: str, org) -> Domain:
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    try:
        return Domain.objects.filter(
            organization=org,
            deleted_at__isnull=True,
        ).get(pk=domain_id)
    except Domain.DoesNotExist:
        raise NotFound("Domain not found.")
    except (OperationalError, ProgrammingError) as e:
        logger.error("DomainService.get DB error: %s", e, extra={"domain_id": domain_id})
        raise ValidationError({"detail": "Service unavailable."})


def update_domain(domain_id: str, data: dict, org, user) -> Domain:
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    if not org.plan or not org.plan.domain_quota:
        raise ValidationError({"detail": "Domain monitoring requires a paid plan."})
    domain = get_domain(domain_id, org)
    for field in ["frequency", "is_active", "notify_email", "slack_webhook_url"]:
        if field in data:
            value = data[field]
            if field == "slack_webhook_url" and not value:
                value = ""
            setattr(domain, field, value)
    domain.updated_by = user
    allowed = DOMAIN_ALLOWED_UPDATE_FIELDS
    safe_fields = [f for f in data if f in allowed]
    domain.save(update_fields=safe_fields + ["updated_by", "updated_at"])

    try:
        from apps.core.models import AuditLog

        AuditLog.objects.create(
            organization=org,
            actor=user,
            action="UPDATE",
            resource_type="Domain",
            resource_id=str(domain.id),
            changes={f: data[f] for f in safe_fields if f in data},
        )
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "AuditLog update failed for domain %s: %s",
            domain.id,
            e,
            extra={"domain_id": str(domain.id)},
        )

    return domain


def update_status_from_scan(domain, scan) -> None:
    try:
        if scan.malware_detected:
            new_status = "infected"
        elif scan.blacklisted:
            new_status = "blacklisted"
        else:
            new_status = "clean"

        Domain.objects.filter(pk=domain.pk).update(
            last_status=new_status,
            last_scan_id=scan.pk,
            updated_at=timezone.now(),
        )
    except Domain.DoesNotExist:
        logger.warning(
            "update_status_from_scan: domain not found",
            extra={"domain_id": str(domain.pk), "scan_id": str(scan.pk)},
        )
    except ValidationError:
        raise
    except Exception as exc:
        logger.error(
            "update_status_from_scan failed",
            exc_info=True,
            extra={
                "domain_id": str(domain.pk),
                "scan_id": str(scan.pk),
                "exc_type": type(exc).__name__,
            },
        )
        raise


def delete_domain(domain_id: str, org, user) -> None:
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    domain = get_domain(domain_id, org)

    with transaction.atomic():
        now = timezone.now()
        domain.soft_delete()
        from apps.scans.models import Scan

        Scan.objects.filter(
            domain=domain.domain,
            organization=org,
            deleted_at__isnull=True,
        ).update(deleted_at=now, updated_at=now)

    try:
        from apps.core.models import AuditLog

        AuditLog.objects.create(
            organization=org,
            actor=user,
            action="DELETE",
            resource_type="Domain",
            resource_id=str(domain.id),
            changes={"domain": domain.domain},
        )
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "AuditLog delete failed for domain %s: %s",
            domain.id,
            e,
            extra={"domain_id": str(domain.id)},
        )
