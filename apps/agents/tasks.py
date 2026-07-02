import logging
import uuid
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    time_limit=300,
    acks_late=True,
    name="apps.agents.tasks.check_agent_health",
)
def check_agent_health(self, trace_id: str = ""):

    from .models import ServerAgent

    trace_id = trace_id or str(uuid.uuid4())

    try:
        cutoff = timezone.now() - timedelta(days=7)
        last_id = None
        total_updated = 0
        while True:
            qs = ServerAgent.objects.filter(
                status="active",
                last_seen_at__lt=cutoff,
            ).order_by("id")
            if last_id is not None:
                qs = qs.filter(id__gt=last_id)
            batch = list(qs[:100])
            if not batch:
                break
            batch_ids = [a.id for a in batch]

            updated = ServerAgent.objects.filter(
                id__in=batch_ids,
                status="active",
                last_seen_at__lt=cutoff,
            ).update(status="inactive", updated_at=timezone.now())
            total_updated += updated
            last_id = batch[-1].id
        logger.info(
            "check_agent_health: %d agents marked inactive",
            total_updated,
            extra={"trace_id": trace_id},
        )
        if total_updated:
            try:
                from apps.core.models import AuditLog

                AuditLog.objects.create(
                    organization=None,
                    actor=None,
                    action="BULK_AGENTS_DEACTIVATED",
                    resource_type="ServerAgent",
                    resource_id=None,
                    changes={"agents_deactivated": total_updated},
                )
            except Exception as audit_exc:
                logger.error(
                    "check_agent_health: AuditLog failed: %s",
                    audit_exc,
                    extra={"trace_id": trace_id},
                )
    except self.MaxRetriesExceededError as exc:
        from apps.core.models import AuditLog

        try:
            AuditLog.objects.create(
                organization=None,
                actor=None,
                action="task_max_retries_exceeded",
                resource_type="CeleryTask",
                resource_id=self.request.id,
                changes={"task": "check_agent_health", "error": str(exc)},
            )
        except Exception as audit_exc:
            logger.error(
                "AuditLog failed on max_retries: %s",
                audit_exc,
                extra={"trace_id": trace_id},
            )
        logger.error(
            "check_agent_health max_retries exceeded: %s",
            exc,
            extra={"trace_id": trace_id},
        )
        raise
    except Exception as exc:
        logger.error(
            "check_agent_health error: %s",
            exc,
            exc_info=True,
            extra={"trace_id": trace_id},
        )
        from rest_framework.exceptions import ValidationError as DRFValidationError

        if isinstance(exc, DRFValidationError):
            raise
        response = getattr(exc, "response", None)
        if response is not None and 400 <= response.status_code < 500:
            raise

        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
