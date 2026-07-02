import logging
from urllib.parse import urlparse

from celery import Task, shared_task
from django.conf import settings
from django.core.mail import send_mail

from .models import Alert

logger = logging.getLogger(__name__)


class _AlertsBaseTask(Task):

    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            "Task %s permanently failed: %s",
            self.name,
            exc,
            extra={"task_id": task_id},
        )


@shared_task(
    bind=True,
    base=_AlertsBaseTask,
    max_retries=3,
    default_retry_delay=60,
    time_limit=60,
    soft_time_limit=50,
    acks_late=True,
    name="apps.alerts.tasks.send_alert_email",
)
def send_alert_email(self, alert_id: str, trace_id: str = "") -> None:
    try:
        alert = Alert.objects.select_related("organization", "domain", "scan").get(pk=alert_id)
        org_id = str(alert.organization_id) if alert.organization_id else None
        recipients = list(
            alert.organization.members.filter(role__in=["admin", "superadmin"]).values_list(
                "email", flat=True
            )
        )
        if not recipients:
            logger.warning(
                "send_alert_email: no recipients for org %s",
                alert.organization_id,
                extra={"trace_id": trace_id, "org_id": org_id, "alert_id": alert_id},
            )
            return
        domain_label = (
            alert.domain.domain
            if alert.domain
            else (alert.scan.domain if alert.scan else "unknown")
        )
        subject = f"[Sucuri] Alert: {alert.type} on {domain_label}"
        message = (
            f"Alert type: {alert.type}\n"
            f"Severity: {alert.severity}\n"
            f"Domain: {domain_label}\n\n"
            f"Title: {alert.title}\n\n"
            f"Message: {alert.description}"
        )
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=True,
        )
        logger.info(
            "send_alert_email: sent for alert %s",
            alert_id,
            extra={"trace_id": trace_id, "org_id": org_id, "alert_id": alert_id},
        )
    except Alert.DoesNotExist:
        logger.warning(
            "send_alert_email: alert %s not found",
            alert_id,
            extra={"trace_id": trace_id, "org_id": None, "alert_id": alert_id},
        )
    except Exception as exc:
        logger.error(
            "send_alert_email: error %s",
            exc,
            extra={"trace_id": trace_id, "org_id": None, "alert_id": alert_id},
        )

        raise self.retry(exc=exc)


def _validate_slack_url(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            return False
        host = parsed.netloc.lower()
        host_without_port = host.split(":")[0]
        if host_without_port != "hooks.slack.com":
            return False
        if not parsed.path.startswith("/services/"):
            return False
        return True
    except (ValueError, AttributeError) as exc:
        logger.debug("_validate_slack_url: parse error for url: %s", exc)
        return False


@shared_task(
    bind=True,
    base=_AlertsBaseTask,
    max_retries=3,
    default_retry_delay=60,
    time_limit=30,
    soft_time_limit=25,
    acks_late=True,
    name="apps.alerts.tasks.send_slack_webhook",
)
def send_slack_webhook(self, alert_id: str, organization_id: str, trace_id: str = ""):
    import requests as req_lib

    from apps.domains.models import Domain

    _ctx = {"trace_id": trace_id, "org_id": str(organization_id), "alert_id": alert_id}

    try:
        alert = Alert.objects.select_related("organization", "scan").get(
            pk=alert_id,
            organization_id=organization_id,
        )
        scan_domain = alert.scan.domain if alert.scan else None
        if not scan_domain:
            return
        domain_obj = (
            Domain.objects.filter(
                organization_id=organization_id,
                domain=scan_domain,
                slack_webhook_url__isnull=False,
            )
            .exclude(slack_webhook_url="")
            .first()
        )
        if not domain_obj:
            return
        webhook_url = domain_obj.slack_webhook_url
        if not _validate_slack_url(webhook_url):
            logger.warning(
                "send_slack_webhook: blocked invalid Slack webhook URL for alert %s (org %s)",
                alert_id,
                organization_id,
                extra=_ctx,
            )
            return
        payload = {
            "text": f'*{alert.type.replace("_", " ").title()}* on `{scan_domain}`',
            "attachments": [
                {
                    "color": "#dc2626" if alert.severity == "critical" else "#f59e0b",
                    "fields": [
                        {
                            "title": "Severity",
                            "value": alert.severity.upper(),
                            "short": True,
                        },
                        {"title": "Type", "value": alert.type, "short": True},
                        {
                            "title": "Message",
                            "value": alert.description or "",
                            "short": False,
                        },
                    ],
                }
            ],
        }
        response = req_lib.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
    except Alert.DoesNotExist:
        logger.warning(
            "send_slack_webhook: alert %s not found, not retrying",
            alert_id,
            extra=_ctx,
        )
        return
    except req_lib.exceptions.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        if exc.response is not None and exc.response.status_code < 500:
            logger.error(
                "send_slack_webhook: client error HTTP %s for alert %s (org %s) — not retrying",
                status_code,
                alert_id,
                organization_id,
                extra=_ctx,
            )
            return
        logger.error(
            "send_slack_webhook: server error HTTP %s for alert %s (org %s) — retrying",
            status_code,
            alert_id,
            organization_id,
            extra=_ctx,
        )
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
    except req_lib.exceptions.RequestException as exc:

        logger.error(
            "send_slack_webhook: request error for alert %s (org %s) — retrying",
            alert_id,
            organization_id,
            extra=_ctx,
        )
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
    except Exception as exc:

        logger.error(
            "send_slack_webhook unexpected error for alert %s: %s",
            alert_id,
            exc,
            extra=_ctx,
        )
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
