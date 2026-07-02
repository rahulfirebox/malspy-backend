import logging
from datetime import timedelta

from celery import Task, shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.utils import timezone

logger = logging.getLogger(__name__)


class _CoreBaseTask(Task):

    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.critical(
            "Task %s permanently failed: %s",
            self.name,
            exc,
            extra={"task_id": task_id},
        )


@shared_task(
    bind=True,
    base=_CoreBaseTask,
    max_retries=3,
    default_retry_delay=300,
    time_limit=4200,
    soft_time_limit=3600,
    acks_late=True,
    name="apps.core.tasks.purge_expired_data",
)
def purge_expired_data(self):
    from django.conf import settings

    retention_days = getattr(settings, "DATA_RETENTION_DAYS", 90)
    cutoff = timezone.now() - timedelta(days=retention_days)

    from apps.accounts.models import PasswordResetToken
    from apps.alerts.models import Alert
    from apps.domains.models import Domain
    from apps.scans.models import Scan

    total_deleted = {}

    try:
        count = 0
        last_id = None
        while True:
            qs = PasswordResetToken.objects.filter(expires_at__lt=timezone.now())
            if last_id is not None:
                qs = qs.filter(id__gt=last_id)
            batch = list(qs.order_by("id").values_list("id", flat=True)[:500])
            if not batch:
                break
            deleted_count, _ = PasswordResetToken.objects.filter(id__in=batch).delete()
            count += deleted_count
            last_id = batch[-1]
            logger.info(
                "purge_expired_data: purged %d password_reset_tokens in batch",
                deleted_count,
                extra={"batch_count": deleted_count},
            )
        total_deleted["password_reset_tokens"] = count
    except SoftTimeLimitExceeded:
        raise
    except Exception as exc:
        logger.warning(
            "purge_expired_data: token cleanup failed — %s",
            exc,
            extra={"model": "password_reset_tokens"},
        )

    for model_name, Model in [("domains", Domain), ("scans", Scan), ("alerts", Alert)]:

        try:
            model_total = 0
            while True:
                ids = list(
                    Model.objects.filter(
                        deleted_at__isnull=False,
                        deleted_at__lt=cutoff,
                    ).values_list("id", flat=True)[:500]
                )
                if not ids:
                    break
                deleted_count, _ = Model.objects.filter(id__in=ids).delete()
                model_total += deleted_count
                logger.info(
                    "purge_expired_data: purged %d %s in batch",
                    deleted_count,
                    model_name,
                    extra={"model": model_name, "batch_count": deleted_count},
                )
            total_deleted[model_name] = model_total
        except SoftTimeLimitExceeded:
            raise
        except Exception as exc:
            logger.warning(
                "purge_expired_data: %s cleanup failed — %s",
                model_name,
                exc,
                extra={"model": model_name},
            )

    logger.info(
        "purge_expired_data: completed — %s",
        total_deleted,
        extra={"totals": total_deleted},
    )
    return total_deleted
