import calendar
import ipaddress
import logging
import socket
import time
import uuid
from datetime import timedelta

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.core.cache import cache
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)

_SIG_STATUS_TTL = 86400


BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_ssrf_blocked(hostname: str) -> bool:
    try:
        results = socket.getaddrinfo(hostname, None)
        for result in results:
            ip_str = result[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
                for blocked in BLOCKED_NETWORKS:
                    if ip in blocked:
                        return True
            except ValueError as exc:
                logger.debug(
                    "_is_ssrf_blocked: could not parse IP %s: %s",
                    ip_str,
                    exc,
                    extra={"ip_str": ip_str},
                )
    except socket.gaierror as exc:
        logger.debug(
            "_is_ssrf_blocked: DNS resolution failed for %s: %s",
            hostname,
            exc,
            extra={"hostname": hostname},
        )
    return False


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    time_limit=300,
    soft_time_limit=240,
    acks_late=True,
    name="apps.scans.tasks.trigger_scan",
)
def trigger_scan(self, scan_id: str, trace_id: str = ""):
    from .models import Scan
    from .services import call_sucuri_api, parse_sucuri_response

    trace_id = trace_id or str(uuid.uuid4())

    try:
        scan = Scan.objects.select_related("organization__plan").get(pk=scan_id)
    except Scan.DoesNotExist:
        logger.error("trigger_scan: Scan %s not found", scan_id, extra={"trace_id": trace_id})
        return

    try:
        scan.status = "scanning"
        scan.save(update_fields=["status", "updated_at"])

        if _is_ssrf_blocked(scan.domain):
            raise ValidationError(
                f"Domain {scan.domain} resolves to a private/reserved IP (SSRF protection)"
            )

        raw = call_sucuri_api(scan.domain)
        parsed = parse_sucuri_response(raw, scan.domain)

        scan.site_info = parsed["site_info"]
        scan.software_info = parsed["software_info"]
        scan.tls_info = parsed["tls_info"]
        scan.links_info = parsed["links_info"]
        scan.ratings_info = parsed["ratings_info"]
        scan.recommendations = parsed["recommendations"]
        scan.blacklist_info = parsed["blacklist_info"]
        scan.blacklisted = parsed["blacklisted"]
        scan.overall_rating = parsed["overall_rating"]
        scan.sucuri_raw = raw
        scan.save(
            update_fields=[
                "status",
                "site_info",
                "software_info",
                "tls_info",
                "links_info",
                "ratings_info",
                "recommendations",
                "blacklist_info",
                "blacklisted",
                "overall_rating",
                "sucuri_raw",
                "updated_at",
            ]
        )

        from django.db import transaction

        plan_slug = (
            "public"
            if scan.is_public
            else (
                scan.organization.plan.slug
                if scan.organization and scan.organization.plan
                else "free"
            )
        )
        logger.info(
            "trigger_scan: scan %s completed API call, chaining process_scan_result",
            scan_id,
            extra={"trace_id": trace_id},
        )
        with transaction.atomic():
            transaction.on_commit(
                lambda: process_scan_result.delay(scan_id, plan_slug, trace_id=trace_id)
            )

    except SoftTimeLimitExceeded:
        logger.error(
            "trigger_scan soft time limit exceeded for %s",
            scan_id,
            extra={"trace_id": trace_id},
        )
        Scan.objects.filter(pk=scan_id).update(status="failed", updated_at=timezone.now())
    except ValidationError as domain_exc:
        logger.warning(
            "trigger_scan non-retryable ValidationError for %s: %s",
            scan_id,
            domain_exc,
            extra={"trace_id": trace_id},
        )
        Scan.objects.filter(pk=scan_id).update(status="failed", updated_at=timezone.now())
    except self.MaxRetriesExceededError:
        logger.error(
            "trigger_scan max_retries exceeded for scan %s",
            scan_id,
            extra={"trace_id": trace_id},
        )
        from apps.core.models import AuditLog

        try:
            scan_obj = Scan.objects.filter(pk=scan_id).first()
            if scan_obj:
                AuditLog.objects.create(
                    organization=scan_obj.organization,
                    actor=None,
                    action="scan_task_failed_permanently",
                    resource_type="Scan",
                    resource_id=str(scan_id),
                    changes={"task": "trigger_scan", "retries": self.max_retries},
                )
        except Exception as audit_exc:
            logger.error("AuditLog failed: %s", audit_exc, extra={"trace_id": trace_id})
        Scan.objects.filter(pk=scan_id).update(status="failed", updated_at=timezone.now())
        raise
    except Exception as exc:
        logger.error(
            "trigger_scan error for %s: %s",
            scan_id,
            exc,
            exc_info=True,
            extra={"trace_id": trace_id},
        )

        if self.request.retries < self.max_retries:
            countdown = 60 * (2**self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        Scan.objects.filter(pk=scan_id).update(status="failed", updated_at=timezone.now())


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    time_limit=300,
    soft_time_limit=240,
    acks_late=True,
    name="apps.scans.tasks.process_scan_result",
)
def process_scan_result(self, scan_id: str, plan_slug: str = "free", trace_id: str = ""):
    from .models import Scan
    from .scanner import run_layer1_scan
    from .ssl_checker import check_tls_direct
    from .whois_checker import get_whois_info

    trace_id = trace_id or str(uuid.uuid4())

    try:
        scan = Scan.objects.select_related("organization__plan").get(pk=scan_id)
    except Scan.DoesNotExist:
        logger.error(
            "process_scan_result: Scan %s not found",
            scan_id,
            extra={"trace_id": trace_id},
        )
        return

    start_ms = int(time.time() * 1000)

    try:

        try:
            whois_data = get_whois_info(scan.domain)
            scan.whois_info = whois_data
        except Exception as e:
            logger.warning("WHOIS error for %s: %s", scan.domain, e, extra={"trace_id": trace_id})
            scan.whois_info = {"error": str(e)}

        try:
            tls_direct = check_tls_direct(scan.domain)
            scan.tls_direct_info = tls_direct
        except Exception as e:
            logger.warning(
                "TLS direct check error for %s: %s",
                scan.domain,
                e,
                extra={"trace_id": trace_id},
            )
            scan.tls_direct_info = {"error": str(e)}

        try:
            malware_result = run_layer1_scan(scan.url)
            scan.malware_info = malware_result
            scan.malware_detected = malware_result.get("detected", False)
        except Exception as e:
            logger.error(
                "Layer1 scan error for %s: %s",
                scan.domain,
                e,
                exc_info=True,
                extra={"trace_id": trace_id},
            )
            scan.malware_info = {"error": str(e), "detected": False}
            scan.malware_detected = False

        elapsed = int(time.time() * 1000) - start_ms
        scan.scan_duration_ms = elapsed
        scan.status = "completed"
        scan.completed_at = timezone.now()
        scan.save(
            update_fields=[
                "whois_info",
                "tls_direct_info",
                "malware_info",
                "malware_detected",
                "scan_duration_ms",
                "status",
                "completed_at",
                "updated_at",
            ]
        )
        logger.info(
            "process_scan_result: scan %s completed in %dms",
            scan_id,
            elapsed,
            extra={"trace_id": trace_id},
        )

        try:
            from .services import _set_cached_result

            _set_cached_result(
                scan.domain,
                plan_slug,
                {
                    "malware_info": scan.malware_info,
                    "tls_direct_info": scan.tls_direct_info,
                    "whois_info": scan.whois_info,
                    "malware_detected": scan.malware_detected,
                    "status": scan.status,
                },
            )
        except Exception as exc:
            logger.warning(
                "Cache write failed for scan %s: %s",
                scan_id,
                exc,
                extra={"trace_id": trace_id},
            )

        if scan.organization:
            try:
                from apps.domains.models import Domain
                from apps.domains.services import update_status_from_scan

                domain_obj = Domain.objects.filter(
                    organization=scan.organization,
                    domain=scan.domain,
                    deleted_at__isnull=True,
                    is_active=True,
                ).first()
                if domain_obj:
                    update_status_from_scan(domain_obj, scan)
            except Exception as e:
                logger.error(
                    "Domain status update failed for scan %s: %s",
                    scan_id,
                    e,
                    extra={"trace_id": trace_id},
                )

        try:
            from apps.alerts.services import generate_alerts_from_scan

            generate_alerts_from_scan(scan)
        except Exception as e:
            logger.error(
                "Alert generation failed for scan %s: %s",
                scan_id,
                e,
                extra={"trace_id": trace_id},
            )

        if (
            scan.organization
            and scan.organization.plan
            and scan.organization.plan.browser_scan_enabled
        ):
            from django.db import transaction

            with transaction.atomic():
                transaction.on_commit(lambda: run_browser_scan.delay(scan_id, trace_id=trace_id))

        if scan.notify_email and scan.created_by and scan.created_by.notify_email:
            try:
                from django.db import transaction

                with transaction.atomic():
                    transaction.on_commit(lambda: send_scan_email.delay(scan_id, trace_id=trace_id))
            except Exception as e:
                logger.error(
                    "Could not queue scan email for %s: %s",
                    scan_id,
                    e,
                    extra={"trace_id": trace_id},
                )

    except SoftTimeLimitExceeded:
        logger.error(
            "process_scan_result soft time limit exceeded for %s",
            scan_id,
            extra={"trace_id": trace_id},
        )
        Scan.objects.filter(pk=scan_id).update(status="failed", updated_at=timezone.now())
    except self.MaxRetriesExceededError:
        logger.error(
            "process_scan_result max_retries exceeded for scan %s",
            scan_id,
            extra={"trace_id": trace_id},
        )
        from apps.core.models import AuditLog

        try:
            scan_obj = Scan.objects.filter(pk=scan_id).first()
            if scan_obj:
                AuditLog.objects.create(
                    organization=scan_obj.organization,
                    actor=None,
                    action="scan_task_failed_permanently",
                    resource_type="Scan",
                    resource_id=str(scan_id),
                    changes={
                        "task": "process_scan_result",
                        "retries": self.max_retries,
                    },
                )
        except Exception as audit_exc:
            logger.error("AuditLog failed: %s", audit_exc, extra={"trace_id": trace_id})
        Scan.objects.filter(pk=scan_id).update(status="failed", updated_at=timezone.now())
        raise
    except Exception as exc:
        logger.error(
            "process_scan_result error for %s: %s",
            scan_id,
            exc,
            exc_info=True,
            extra={"trace_id": trace_id},
        )

        if self.request.retries < self.max_retries:
            countdown = 60 * (2**self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)
        Scan.objects.filter(pk=scan_id).update(status="failed", updated_at=timezone.now())


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    time_limit=180,
    soft_time_limit=150,
    acks_late=True,
    queue="browser_scans",
    name="apps.scans.tasks.run_browser_scan",
)
def run_browser_scan(self, scan_id: str, trace_id: str = ""):
    from .models import Scan

    trace_id = trace_id or str(uuid.uuid4())

    try:
        scan = Scan.objects.select_related("organization__plan").get(pk=scan_id)
    except Scan.DoesNotExist:
        logger.error("run_browser_scan: Scan %s not found", scan_id, extra={"trace_id": trace_id})
        return

    if not scan.organization:
        return

    lock_key = f"browser_scan_lock:{scan.organization_id}"
    acquired = cache.add(lock_key, "1", timeout=300)
    if not acquired:
        logger.info(
            "Browser scan already running for org %s, skipping %s",
            scan.organization_id,
            scan_id,
            extra={"trace_id": trace_id},
        )
        return

    try:
        from .browser_scanner import BrowserScanner

        browser_result = BrowserScanner().run(scan.url)
        scan.browser_scan_info = browser_result
        if browser_result["detected"]:
            scan.malware_detected = True
        scan.save(update_fields=["browser_scan_info", "malware_detected", "updated_at"])
        logger.info("run_browser_scan: scan %s completed", scan_id, extra={"trace_id": trace_id})

        try:
            from apps.alerts.services import generate_browser_alerts

            generate_browser_alerts(scan)
        except Exception as e:
            logger.error(
                "Browser alert generation failed for %s: %s",
                scan_id,
                e,
                extra={"trace_id": trace_id},
            )

    except SoftTimeLimitExceeded:
        logger.error(
            "run_browser_scan soft time limit for %s",
            scan_id,
            extra={"trace_id": trace_id},
        )
        scan.browser_scan_info = {"error": "Scan timed out", "detected": False}
        scan.save(update_fields=["browser_scan_info", "updated_at"])
    except self.MaxRetriesExceededError:
        logger.error(
            "run_browser_scan max_retries exceeded for scan %s",
            scan_id,
            extra={"trace_id": trace_id},
        )
        from apps.core.models import AuditLog

        try:
            scan_obj = Scan.objects.filter(pk=scan_id).first()
            if scan_obj:
                AuditLog.objects.create(
                    organization=scan_obj.organization,
                    actor=None,
                    action="scan_browser_task_failed_permanently",
                    resource_type="Scan",
                    resource_id=str(scan_id),
                    changes={"task": "run_browser_scan", "retries": self.max_retries},
                )
        except Exception as audit_exc:
            logger.error("AuditLog failed: %s", audit_exc, extra={"trace_id": trace_id})
        Scan.objects.filter(pk=scan_id).update(status="failed")
        raise
    except Exception as exc:
        logger.error(
            "run_browser_scan error for %s: %s",
            scan_id,
            exc,
            exc_info=True,
            extra={"trace_id": trace_id},
        )

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=120 * (2**self.request.retries))
        scan.browser_scan_info = {"error": "Browser scan failed.", "detected": False}
        scan.save(update_fields=["browser_scan_info", "updated_at"])
    finally:
        cache.delete(lock_key)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    time_limit=60,
    soft_time_limit=50,
    acks_late=True,
    name="apps.scans.tasks.send_scan_email",
)
def send_scan_email(self, scan_id: str, trace_id: str = ""):
    from .models import Scan

    trace_id = trace_id or str(uuid.uuid4())

    try:
        scan = Scan.objects.select_related("created_by", "organization").get(pk=scan_id)
        if not scan.created_by or not scan.created_by.email:
            return

        logger.info(
            "Scan completion email queued for %s (scan %s)",
            scan.created_by.email,
            scan_id,
            extra={"trace_id": trace_id},
        )
    except Scan.DoesNotExist:
        logger.warning("send_scan_email: scan %s not found", scan_id, extra={"trace_id": trace_id})
    except Exception as exc:
        logger.error("send_scan_email error: %s", exc, extra={"trace_id": trace_id})

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30 * (2**self.request.retries))


@shared_task(
    bind=True,
    max_retries=1,
    soft_time_limit=110,
    time_limit=120,
    acks_late=True,
    name="apps.scans.tasks.generate_pdf_report",
)
def generate_pdf_report(self, scan_id: str) -> str | None:
    from .models import Scan

    try:
        scan = Scan.objects.select_related("organization__plan").get(pk=scan_id)
        if scan.status != "completed":
            logger.warning(
                "generate_pdf_report called on non-completed scan %s",
                scan_id,
                extra={"scan_id": str(scan_id), "status": scan.status},
            )
            return None

        import io

        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        c.setFont("Helvetica-Bold", 18)
        c.drawString(50, height - 50, "Security Scan Report")
        c.setFont("Helvetica", 12)
        c.drawString(50, height - 80, f"Domain: {scan.domain}")
        c.drawString(50, height - 100, f"URL: {scan.url}")
        c.drawString(50, height - 120, f"Status: {scan.status}")
        c.drawString(50, height - 140, f'Rating: {scan.overall_rating or "N/A"}')
        c.drawString(50, height - 160, f"Malware Detected: {scan.malware_detected}")
        c.drawString(50, height - 180, f"Blacklisted: {scan.blacklisted}")
        if scan.completed_at:
            c.drawString(
                50,
                height - 200,
                f'Completed: {scan.completed_at.strftime("%Y-%m-%d %H:%M UTC")}',
            )

        if scan.malware_info and scan.malware_info.get("findings"):
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, height - 240, "Malware Findings:")
            c.setFont("Helvetica", 10)
            y = height - 260
            for finding in scan.malware_info["findings"][:10]:
                c.drawString(
                    70,
                    y,
                    f"[{finding.get('severity', '').upper()}] {finding.get('name', '')}",
                )
                y -= 20
                c.drawString(90, y, f"URL: {finding.get('source_url', '')[:80]}")
                y -= 20

        c.showPage()
        c.save()
        buffer.seek(0)
        return buffer.getvalue()

    except Exception as exc:
        logger.error(
            "generate_pdf_report error for %s: %s",
            scan_id,
            exc,
            exc_info=True,
            extra={"scan_id": str(scan_id)},
        )
        return None


def _advance_one_month(dt):
    month = dt.month + 1
    year = dt.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    soft_time_limit=290,
    time_limit=300,
    acks_late=True,
    name="apps.scans.tasks.reset_monthly_quota",
)
def reset_monthly_quota(self):
    from apps.accounts.models import Organization
    from apps.core.models import AuditLog

    try:
        now = timezone.now()
        next_reset = _advance_one_month(now)
        last_id = 0
        total_updated = 0

        while True:
            batch = list(
                Organization.objects.filter(
                    id__gt=last_id,
                    quota_reset_at__lte=now,
                )
                .order_by("id")
                .values_list("id", flat=True)[:500]
            )
            if not batch:
                break
            updated = Organization.objects.filter(id__in=batch).update(
                scan_quota_used=0,
                quota_reset_at=next_reset,
                updated_at=timezone.now(),
            )
            total_updated += updated
            last_id = batch[-1]
            logger.info(
                "reset_monthly_quota: processed up to id=%s",
                last_id,
                extra={"last_id": last_id, "running_total": total_updated},
            )

        null_updated = Organization.objects.filter(quota_reset_at__isnull=True).update(
            scan_quota_used=0,
            quota_reset_at=next_reset,
            updated_at=timezone.now(),
        )
        total_updated += null_updated

        logger.info(
            "reset_monthly_quota: completed — %d orgs reset (%d had NULL quota_reset_at)",
            total_updated,
            null_updated,
            extra={"total_updated": total_updated, "null_initialized": null_updated},
        )

        try:
            AuditLog.objects.create(
                organization=None,
                actor=None,
                action="quota_reset",
                resource_type="Organization",
                resource_id=None,
                changes={
                    "total_reset": total_updated,
                    "null_initialized": null_updated,
                },
            )
        except Exception as audit_exc:
            logger.error(
                "reset_monthly_quota: AuditLog failed: %s",
                audit_exc,
                extra={"total_updated": total_updated},
            )

    except self.MaxRetriesExceededError:
        logger.error(
            "reset_monthly_quota: max_retries exceeded",
            extra={"retries": self.max_retries},
        )
        try:
            AuditLog.objects.create(
                organization=None,
                actor=None,
                action="quota_reset_failed_permanently",
                resource_type="Organization",
                resource_id=None,
                changes={"task": "reset_monthly_quota", "retries": self.max_retries},
            )
        except Exception as audit_create_exc:
            logger.warning(
                "reset_monthly_quota: AuditLog create failed after max retries",
                exc_info=True,
                extra={"error": str(audit_create_exc)},
            )
        raise
    except Exception as exc:
        logger.error(
            "reset_monthly_quota error: %s",
            exc,
            exc_info=True,
            extra={"retries": self.request.retries},
        )

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=300 * (2**self.request.retries))


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    soft_time_limit=290,
    time_limit=300,
    acks_late=True,
    name="apps.scans.tasks.update_malware_signatures",
)
def update_malware_signatures(self):
    try:
        from .models import MalwareSignature

        sig_count = MalwareSignature.objects.filter(is_active=True).count()
        status_payload = {
            "status": "stub_no_feed_integration",
            "signature_count": sig_count,
            "run_at": timezone.now().isoformat(),
        }
        from django.core.cache import cache as djcache

        _SIG_STATUS_KEY = "malware_signature_update_status"
        djcache.set(_SIG_STATUS_KEY, status_payload, timeout=_SIG_STATUS_TTL)
        logger.warning(
            "update_malware_signatures: no external feed configured, running as stub; %d active signatures in DB",
            sig_count,
            extra={"signature_count": sig_count},
        )
    except Exception as exc:
        logger.error(
            "update_malware_signatures error: %s",
            exc,
            exc_info=True,
            extra={"retries": self.request.retries},
        )

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=300 * (2**self.request.retries))


@shared_task(
    bind=True,
    max_retries=1,
    soft_time_limit=110,
    time_limit=120,
    acks_late=True,
    name="apps.scans.tasks.cleanup_stale_scans",
)
def cleanup_stale_scans(self):
    from celery.exceptions import SoftTimeLimitExceeded as _SoftTimeLimitExceeded

    try:
        from .models import Scan

        cutoff = timezone.now() - timedelta(minutes=15)
        now_ts = timezone.now()
        total_updated = 0

        while True:
            ids = list(
                Scan.objects.filter(
                    status__in=["queued", "scanning"],
                    updated_at__lt=cutoff,
                ).values_list("id", flat=True)[:500]
            )
            if not ids:
                break
            batch_updated = Scan.objects.filter(id__in=ids).update(
                status="failed", updated_at=now_ts
            )
            total_updated += batch_updated

        if total_updated:
            logger.info(
                "cleanup_stale_scans: marked %d stale scans as failed",
                total_updated,
                extra={"updated": total_updated},
            )
            try:
                from apps.core.models import AuditLog

                AuditLog.objects.create(
                    organization=None,
                    actor=None,
                    action="BULK_CLEANUP_STALE_SCANS",
                    resource_type="Scan",
                    resource_id=None,
                    changes={"scans_failed": total_updated},
                )
            except Exception as audit_exc:
                logger.error(
                    "cleanup_stale_scans: AuditLog failed: %s",
                    audit_exc,
                    extra={"updated": total_updated},
                )
        else:
            logger.info(
                "cleanup_stale_scans: no stale scans found",
                extra={"updated": 0},
            )
    except _SoftTimeLimitExceeded:
        logger.error(
            "cleanup_stale_scans: soft time limit exceeded",
            extra={"updated_so_far": total_updated if "total_updated" in dir() else 0},
        )
    except Exception as exc:
        logger.error(
            "cleanup_stale_scans error: %s",
            exc,
            exc_info=True,
            extra={"retries": self.request.retries},
        )


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=290,
    time_limit=300,
    acks_late=True,
    name="apps.scans.tasks.send_quota_warning_email",
)
def send_quota_warning_email(self):
    from django.conf import settings
    from django.core.mail import send_mail
    from django.db.models import Q

    from apps.accounts.models import Organization

    try:
        warned = 0
        last_id = 0
        while True:
            orgs = list(
                Organization.objects.filter(
                    Q(id__gt=last_id)
                    & Q(scan_quota_used__gte=0)
                    & Q(plan__scan_quota__gt=0)
                    & Q(scan_quota_used__gte=F("plan__scan_quota") * 80 / 100)
                    & Q(scan_quota_used__lt=F("plan__scan_quota"))
                )
                .select_related("plan", "owner")
                .order_by("id")[:100]
            )
            if not orgs:
                break
            for org in orgs:
                if not org.owner or not org.owner.email:
                    continue
                used = org.scan_quota_used
                limit = org.plan.scan_quota
                percent = int((used / limit) * 100)
                try:
                    body = (
                        "Hi,\n\n"
                        f"Your organisation '{org.name}' has used {used} of {limit} "
                        f"({percent}%) scans this period.\n\n"
                        "Once the limit is reached, new scans will be blocked until the next reset.\n\n"
                        "Upgrade your plan at any time to increase your quota.\n\n"
                        "The Sucuri Team"
                    )
                    send_mail(
                        subject=f"[Sucuri] Scan quota {percent}% used - {org.name}",
                        message=body,
                        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@sucuri.net"),
                        recipient_list=[org.owner.email],
                        fail_silently=False,
                    )
                    warned += 1
                    logger.info(
                        "Quota warning email sent to %s (org %s, %d%%)",
                        org.owner.email,
                        org.id,
                        percent,
                        extra={"org_id": str(org.id), "percent": percent},
                    )
                except Exception as email_exc:
                    logger.error(
                        "Failed to send quota warning to %s: %s",
                        org.owner.email,
                        email_exc,
                        extra={"org_id": str(org.id)},
                    )
            last_id = orgs[-1].id

        exhausted = 0
        last_id = 0
        while True:
            orgs_exhausted = list(
                Organization.objects.filter(
                    Q(id__gt=last_id)
                    & Q(plan__scan_quota__gt=0)
                    & Q(scan_quota_used__gte=F("plan__scan_quota"))
                )
                .select_related("plan", "owner")
                .order_by("id")[:100]
            )
            if not orgs_exhausted:
                break
            for org in orgs_exhausted:
                if not org.owner or not org.owner.email:
                    continue
                limit = org.plan.scan_quota
                try:
                    body = (
                        "Hi,\n\n"
                        f"Your organisation '{org.name}' has reached its scan quota of {limit} scans.\n\n"
                        "New scans are now blocked until your quota resets.\n\n"
                        "Upgrade your plan to immediately restore scanning capability.\n\n"
                        "The Sucuri Team"
                    )
                    send_mail(
                        subject=f"[Sucuri] Scan quota exhausted - {org.name}",
                        message=body,
                        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@sucuri.net"),
                        recipient_list=[org.owner.email],
                        fail_silently=False,
                    )
                    exhausted += 1
                    logger.info(
                        "Quota exhausted email sent to %s (org %s)",
                        org.owner.email,
                        org.id,
                        extra={"org_id": str(org.id)},
                    )
                except Exception as email_exc:
                    logger.error(
                        "Failed to send quota exhausted email to %s: %s",
                        org.owner.email,
                        email_exc,
                        extra={"org_id": str(org.id)},
                    )
            last_id = orgs_exhausted[-1].id

        logger.info(
            "send_quota_warning_email: %d orgs warned, %d orgs exhausted",
            warned,
            exhausted,
            extra={"warned": warned, "exhausted": exhausted},
        )

    except Exception as exc:
        logger.error(
            "send_quota_warning_email error: %s",
            exc,
            exc_info=True,
            extra={"retries": self.request.retries},
        )

        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
