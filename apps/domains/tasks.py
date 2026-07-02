import logging
import socket
import ssl
import uuid
from datetime import datetime
from datetime import timezone as dt_tz

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    time_limit=300,
    soft_time_limit=240,
    acks_late=True,
    name="apps.domains.tasks.trigger_scheduled_scan",
)
def trigger_scheduled_scan(self, domain_id: str, trace_id: str = ""):
    from apps.scans.services import create_scan

    from .models import Domain

    trace_id = trace_id or str(uuid.uuid4())

    try:
        domain = Domain.objects.select_related("organization__plan", "organization__owner").get(
            pk=domain_id, is_active=True, deleted_at__isnull=True
        )
    except Domain.DoesNotExist:
        logger.warning(
            "trigger_scheduled_scan: domain %s not found or inactive",
            domain_id,
            extra={"trace_id": trace_id, "domain_id": domain_id},
        )
        return

    org = domain.organization
    if not org or not org.plan or not org.plan.scheduled_scans:
        logger.info(
            "Scheduled scans not enabled for domain %s (plan: %s)",
            domain_id,
            org.plan.slug if org and org.plan else None,
            extra={"trace_id": trace_id, "domain_id": domain_id},
        )
        return

    user = org.owner

    try:
        scan = create_scan(
            data={
                "url": f"https://{domain.domain}",
                "notify_email": domain.notify_email,
            },
            org=org,
            user=user,
            is_scheduled=True,
        )
        domain.last_scan = scan
        domain.save(update_fields=["last_scan", "updated_at"])
        logger.info(
            "Scheduled scan triggered for domain %s (scan %s)",
            domain.domain,
            scan.id,
            extra={
                "trace_id": trace_id,
                "domain_id": domain_id,
                "scan_id": str(scan.id),
            },
        )
        try:
            from apps.core.models import AuditLog

            AuditLog.objects.create(
                organization=org,
                actor=user,
                action="scan_scheduled_triggered",
                resource_type="Domain",
                resource_id=str(domain_id),
                changes={"scan_id": str(scan.id), "domain": domain.domain},
            )
        except Exception as audit_exc:
            logger.error(
                "AuditLog failed for trigger_scheduled_scan: %s",
                audit_exc,
                extra={"trace_id": trace_id, "domain_id": domain_id},
            )
    except SoftTimeLimitExceeded:
        logger.error(
            "trigger_scheduled_scan soft time limit for %s",
            domain_id,
            extra={"trace_id": trace_id, "domain_id": domain_id},
        )
    except self.MaxRetriesExceededError:
        logger.error(
            "trigger_scheduled_scan max_retries exceeded for domain %s",
            domain_id,
            extra={"trace_id": trace_id, "domain_id": domain_id},
        )
        try:
            from apps.core.models import AuditLog

            AuditLog.objects.create(
                organization=org,
                actor=None,
                action="scan_schedule_failed",
                resource_type="Domain",
                resource_id=str(domain_id),
                changes={"task": "trigger_scheduled_scan", "retries": self.max_retries},
            )
        except Exception as audit_exc:
            logger.error(
                "AuditLog failed after max retries: %s",
                audit_exc,
                extra={"trace_id": trace_id, "domain_id": domain_id},
            )
        raise
    except Exception as exc:
        logger.error(
            "trigger_scheduled_scan error for %s: %s",
            domain_id,
            exc,
            exc_info=True,
            extra={"trace_id": trace_id, "domain_id": domain_id},
        )

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    time_limit=300,
    soft_time_limit=240,
    acks_late=True,
    name="apps.domains.tasks.check_tls_expiry",
)
def check_tls_expiry(self, trace_id: str = ""):
    from apps.alerts.models import Alert
    from apps.domains.models import Domain

    trace_id = trace_id or str(uuid.uuid4())

    try:
        logger.info(
            "check_tls_expiry: starting",
            extra={"trace_id": trace_id},
        )
        checked = 0
        last_id = None

        while True:
            qs = Domain.objects.filter(is_active=True, deleted_at__isnull=True).select_related(
                "organization"
            )
            if last_id is not None:
                qs = qs.filter(id__gt=last_id)
            batch = list(qs.order_by("id")[:200])
            if not batch:
                break
            last_id = batch[-1].id

            for domain in batch:
                try:
                    ctx = ssl.create_default_context()
                    with ctx.wrap_socket(socket.socket(), server_hostname=domain.domain) as s:
                        s.settimeout(10)
                        s.connect((domain.domain, 443))
                        cert = s.getpeercert()

                    expire_str = cert["notAfter"]
                    expire_dt = datetime.strptime(expire_str, "%b %d %H:%M:%S %Y %Z").replace(
                        tzinfo=dt_tz.utc
                    )
                    days_left = (expire_dt - datetime.now(dt_tz.utc)).days

                    if days_left <= 30:
                        severity = "critical" if days_left <= 7 else "high"
                        title = f"TLS certificate expires in {days_left} days"
                        description = (
                            f"Certificate for {domain.domain} expires on {expire_dt.date()}."
                        )
                        with transaction.atomic():
                            try:
                                alert, created = Alert.objects.get_or_create(
                                    organization=domain.organization,
                                    domain=domain,
                                    type="tls_expiring",
                                    is_resolved=False,
                                    defaults={
                                        "severity": severity,
                                        "title": title,
                                        "description": description,
                                    },
                                )
                            except IntegrityError:

                                alert = Alert.objects.filter(
                                    organization=domain.organization,
                                    domain=domain,
                                    type="tls_expiring",
                                    is_resolved=False,
                                ).first()
                                created = False
                                if alert is None:
                                    continue
                            if not created:
                                alert.severity = severity
                                alert.title = title
                                alert.description = description
                                alert.save(
                                    update_fields=[
                                        "severity",
                                        "title",
                                        "description",
                                        "updated_at",
                                    ]
                                )

                    checked += 1
                except (ssl.SSLError, socket.timeout, OSError) as exc:
                    logger.warning(
                        "check_tls_expiry: TLS check failed for %s -- %s",
                        domain.domain,
                        exc,
                        extra={"trace_id": trace_id, "domain": domain.domain},
                    )
                except Exception as exc:
                    logger.error(
                        "check_tls_expiry: unexpected error for %s -- %s",
                        domain.domain,
                        exc,
                        exc_info=True,
                        extra={"trace_id": trace_id, "domain": domain.domain},
                    )

        logger.info(
            "check_tls_expiry: checked %d domains",
            checked,
            extra={"trace_id": trace_id, "checked": checked},
        )

    except SoftTimeLimitExceeded:
        logger.error(
            "check_tls_expiry: soft time limit exceeded",
            extra={"trace_id": trace_id},
        )
    except self.MaxRetriesExceededError:
        logger.error(
            "check_tls_expiry: max_retries exceeded",
            extra={"trace_id": trace_id},
        )
        raise
    except Exception as exc:
        logger.error(
            "check_tls_expiry: top-level error: %s",
            exc,
            exc_info=True,
            extra={"trace_id": trace_id},
        )

        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    time_limit=7200,
    soft_time_limit=6600,
    acks_late=True,
    name="apps.domains.tasks.dispatch_scheduled_scans",
)
def dispatch_scheduled_scans(self, trace_id: str = ""):
    from .models import Domain

    trace_id = trace_id or str(uuid.uuid4())

    try:
        now = timezone.now()
        last_id = None
        dispatched = 0

        while True:
            qs = (
                Domain.objects.filter(
                    is_active=True,
                    deleted_at__isnull=True,
                    next_scan_at__lte=now,
                    organization__plan__scheduled_scans=True,
                )
                .select_related("organization__plan")
                .order_by("id")
            )
            if last_id is not None:
                qs = qs.filter(id__gt=last_id)
            batch = list(qs.values_list("id", flat=True)[:200])
            if not batch:
                break
            for domain_id in batch:
                transaction.on_commit(
                    lambda did=domain_id, tid=trace_id: trigger_scheduled_scan.delay(
                        str(did), trace_id=tid
                    )
                )
                dispatched += 1
            last_id = batch[-1]

        logger.info(
            "dispatch_scheduled_scans: dispatched %d scans",
            dispatched,
            extra={"trace_id": trace_id, "dispatched": dispatched},
        )

    except SoftTimeLimitExceeded:
        logger.error(
            "dispatch_scheduled_scans: soft time limit exceeded",
            extra={"trace_id": trace_id},
        )
    except self.MaxRetriesExceededError:
        logger.error(
            "dispatch_scheduled_scans: max_retries exceeded",
            extra={"trace_id": trace_id},
        )
        raise
    except Exception as exc:
        logger.error(
            "dispatch_scheduled_scans: error: %s",
            exc,
            exc_info=True,
            extra={"trace_id": trace_id},
        )

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
