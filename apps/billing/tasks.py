import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    soft_time_limit=290,
    time_limit=300,
    acks_late=True,
    name="apps.billing.tasks.check_plan_expiry",
)
def check_plan_expiry(self):
    from apps.billing.models import Subscription
    from apps.core.models import AuditLog

    try:
        now = timezone.now()
        expired_ids = list(
            Subscription.objects.filter(
                plan_expires_at__lte=now,
                status__in=["active", "trialing"],
                deleted_at__isnull=True,
            ).values_list("id", flat=True)[:500]
        )

        if not expired_ids:
            logger.info(
                "check_plan_expiry: no expired subscriptions found",
                extra={"checked_at": now.isoformat()},
            )
            return

        updated = Subscription.objects.filter(id__in=expired_ids).update(
            status="cancelled",
            cancelled_at=now,
            updated_at=now,
        )

        logger.info(
            "check_plan_expiry: cancelled %d expired subscriptions",
            updated,
            extra={"updated": updated, "checked_at": now.isoformat()},
        )

        try:
            AuditLog.objects.create(
                organization=None,
                actor=None,
                action="plan_expiry_batch_cancelled",
                resource_type="Subscription",
                resource_id=None,
                changes={"cancelled_count": updated, "checked_at": now.isoformat()},
            )
        except Exception as audit_exc:
            logger.error(
                "check_plan_expiry: AuditLog write failed: %s",
                audit_exc,
                extra={"updated": updated},
            )

    except self.MaxRetriesExceededError:
        logger.error(
            "check_plan_expiry: max_retries exceeded",
            extra={"retries": self.max_retries},
        )
        try:
            AuditLog.objects.create(
                organization=None,
                actor=None,
                action="plan_expiry_task_failed_permanently",
                resource_type="Subscription",
                resource_id=None,
                changes={"task": "check_plan_expiry", "retries": self.max_retries},
            )
        except Exception as audit_write_exc:
            logger.error(
                "check_plan_expiry: AuditLog write failed after max retries: %s",
                audit_write_exc,
                extra={"retries": self.max_retries},
            )
        raise
    except Exception as exc:
        logger.error(
            "check_plan_expiry error: %s",
            exc,
            exc_info=True,
            extra={"retries": self.request.retries},
        )

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=120 * (2**self.request.retries))


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    soft_time_limit=540,
    time_limit=600,
    acks_late=True,
    name="apps.billing.tasks.reconcile_financial_records",
)
def reconcile_financial_records(self):
    from django.db import OperationalError

    try:
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now()
        mismatch_count = 0

        from apps.billing.models import Payment, Subscription

        stale_payments = Payment.objects.filter(
            status="pending",
            created_at__lt=now - timedelta(hours=24),
        ).count()
        if stale_payments:
            logger.error(
                "reconcile_financial_records: %d stale pending payments (>24h)",
                stale_payments,
                extra={"stale_payments": stale_payments},
            )
            mismatch_count += stale_payments

        overrun_subscriptions = Subscription.objects.filter(
            status__in=["active", "trialing"],
            plan_expires_at__lt=now - timedelta(hours=2),
            deleted_at__isnull=True,
        ).count()
        if overrun_subscriptions:
            logger.error(
                "reconcile_financial_records: %d subscriptions overdue expiry (>2h)",
                overrun_subscriptions,
                extra={"overrun_subscriptions": overrun_subscriptions},
            )
            mismatch_count += overrun_subscriptions

        if mismatch_count:
            try:
                import sentry_sdk

                sentry_sdk.capture_message(
                    f"Financial reconciliation: {mismatch_count} mismatch(es) detected",
                    level="error",
                    extras={
                        "stale_payments": stale_payments,
                        "overrun_subscriptions": overrun_subscriptions,
                    },
                )
            except Exception as sentry_exc:
                logger.warning(
                    "reconcile_financial_records: sentry_sdk.capture_message failed: %s",
                    sentry_exc,
                    extra={},
                )
        else:
            logger.info(
                "reconcile_financial_records: no mismatches found",
                extra={"checked_at": now.isoformat()},
            )

    except OperationalError as exc:
        logger.error(
            "reconcile_financial_records: DB error: %s",
            exc,
            exc_info=True,
        )

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=300 * (2**self.request.retries))
        logger.critical(
            "reconcile_financial_records: max_retries exceeded",
            extra={"retries": self.max_retries},
        )
        raise
    except Exception as exc:
        logger.error(
            "reconcile_financial_records: unexpected error: %s",
            exc,
            exc_info=True,
        )
        raise
