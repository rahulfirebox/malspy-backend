import ipaddress
import logging
import time
from urllib.parse import urlparse

from django.db import OperationalError, ProgrammingError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.models import AuditLog

from .models import Alert

logger = logging.getLogger(__name__)

_SLACK_WEBHOOK_PREFIX = "https://hooks.slack.com/services/"


def _validate_url_not_ssrf(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValidationError({"url": "Invalid URL."})
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    if addr is not None and (addr.is_private or addr.is_loopback or addr.is_link_local):
        raise ValidationError({"url": "Private IP addresses are not allowed."})


def _validate_webhook_timestamp(timestamp_header_value: str) -> None:
    try:
        ts = int(timestamp_header_value or 0)
    except (TypeError, ValueError):
        ts = 0
    if abs(time.time() - ts) > 300:
        raise ValidationError({"detail": "Webhook timestamp too old."})


def _get_domain_obj(scan):
    if scan.organization is None or not scan.domain:
        return None
    try:
        from apps.domains.models import Domain

        return Domain.objects.filter(
            organization=scan.organization,
            domain=scan.domain,
            deleted_at__isnull=True,
        ).first()
    except ValidationError:
        raise
    except Exception as exc:
        logger.error(
            "_get_domain_obj failed: %s",
            exc,
            exc_info=True,
            extra={"domain": scan.domain if scan else "unknown"},
        )
        raise


def _dispatch_alert_email(alert_id: str) -> None:
    try:
        from .tasks import send_alert_email

        send_alert_email.delay(alert_id)
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "Could not queue send_alert_email for alert %s: %s",
            alert_id,
            e,
            extra={"alert_id": alert_id},
        )


def _open_alert_exists(org, domain, alert_type: str) -> bool:
    return Alert.objects.filter(
        organization=org,
        domain=domain,
        type=alert_type,
        is_resolved=False,
        deleted_at__isnull=True,
    ).exists()


def generate_alerts_from_scan(scan) -> None:
    if scan.organization is None:
        return

    try:
        domain_obj = _get_domain_obj(scan)
        org = scan.organization
        alerts_to_create = []

        if scan.malware_detected and not _open_alert_exists(org, domain_obj, "malware_detected"):
            alerts_to_create.append(
                Alert(
                    organization=org,
                    domain=domain_obj,
                    scan=scan,
                    type="malware_detected",
                    severity="critical",
                    title=f"Malware detected on {scan.domain}",
                    description="Our Layer 1 static scanner found malware signatures in the page source.",
                )
            )

        if scan.blacklisted and not _open_alert_exists(org, domain_obj, "blacklisted"):
            alerts_to_create.append(
                Alert(
                    organization=org,
                    domain=domain_obj,
                    scan=scan,
                    type="blacklisted",
                    severity="critical",
                    title=f"{scan.domain} is blacklisted",
                    description="This domain appears on one or more security blacklists.",
                )
            )

        tls_direct = scan.tls_direct_info or {}
        days_remaining = tls_direct.get("cert_days_remaining")
        if (
            days_remaining is not None
            and 0 <= days_remaining <= 30
            and not _open_alert_exists(org, domain_obj, "tls_expiring")
        ):
            alerts_to_create.append(
                Alert(
                    organization=org,
                    domain=domain_obj,
                    scan=scan,
                    type="tls_expiring",
                    severity="high",
                    title=f"SSL certificate expiring in {days_remaining} days for {scan.domain}",
                    description="Renew your SSL certificate to avoid browser warnings.",
                )
            )

        recommendations = scan.recommendations or {}
        headers_minor = recommendations.get("headers_minor", {})
        if headers_minor and not _open_alert_exists(org, domain_obj, "missing_headers"):
            missing = ", ".join(headers_minor.keys())
            alerts_to_create.append(
                Alert(
                    organization=org,
                    domain=domain_obj,
                    scan=scan,
                    type="missing_headers",
                    severity="low",
                    title=f"Missing security headers on {scan.domain}",
                    description=f"Missing: {missing}",
                )
            )

        if alerts_to_create:
            try:
                with transaction.atomic():

                    created = Alert.objects.bulk_create(
                        alerts_to_create, batch_size=500, ignore_conflicts=True
                    )
                    created_ids = [str(a.id) for a in created if a.id]
                    for aid in created_ids:
                        transaction.on_commit(lambda _id=aid: _dispatch_alert_email(_id))
                    try:
                        AuditLog.objects.create(
                            organization=scan.organization,
                            actor=None,
                            action="ALERTS_GENERATED",
                            resource_type="Alert",
                            resource_id=str(scan.id),
                            changes={
                                "count": len(created_ids),
                                "scan_id": str(scan.id),
                            },
                        )
                    except ValidationError:
                        raise
                    except Exception as audit_exc:
                        logger.error(
                            "AuditLog write failed for bulk alert create scan %s: %s",
                            scan.id,
                            audit_exc,
                            extra={
                                "org_id": str(scan.organization.id),
                                "scan_id": str(scan.id),
                            },
                        )
            except ValidationError:
                raise
            except Exception as e:
                logger.error(
                    "Alert bulk_create failed for scan %s: %s",
                    scan.id,
                    e,
                    extra={
                        "org_id": str(scan.organization.id),
                        "scan_id": str(scan.id),
                    },
                )

        if not scan.malware_detected and not scan.blacklisted and domain_obj:
            _auto_resolve_clean_alerts(scan, domain_obj)

    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "generate_alerts_from_scan error for scan %s: %s",
            scan.id,
            e,
            exc_info=True,
            extra={
                "org_id": str(scan.organization.id) if scan.organization else "unknown",
                "scan_id": str(scan.id),
            },
        )


def _auto_resolve_clean_alerts(scan, domain_obj) -> None:
    try:
        with transaction.atomic():
            resolved_count = Alert.objects.filter(
                organization=scan.organization,
                domain=domain_obj,
                type__in=["malware_detected", "blacklisted"],
                is_resolved=False,
                deleted_at__isnull=True,
            ).update(
                is_resolved=True,
                resolved_by=None,
                resolved_at=timezone.now(),
                resolved_note="Auto-resolved: clean scan completed.",
                updated_at=timezone.now(),
            )
            if resolved_count:
                try:
                    AuditLog.objects.create(
                        organization=scan.organization,
                        actor=None,
                        action="ALERT_AUTO_RESOLVED",
                        resource_type="Alert",
                        resource_id=str(scan.id),
                        changes={
                            "resolved_count": resolved_count,
                            "scan_id": str(scan.id),
                        },
                    )
                except ValidationError:
                    raise
                except Exception as audit_exc:
                    logger.error(
                        "AuditLog write failed for _auto_resolve_clean_alerts scan %s: %s",
                        scan.id,
                        audit_exc,
                        extra={
                            "org_id": (
                                str(scan.organization.id) if scan.organization else "unknown"
                            ),
                            "scan_id": str(scan.id),
                        },
                    )
    except ValidationError:
        raise
    except Exception as exc:
        logger.error(
            "_auto_resolve_clean_alerts failed for scan %s: %s",
            scan.id,
            exc,
            exc_info=True,
            extra={
                "org_id": str(scan.organization.id) if scan.organization else "unknown",
                "scan_id": str(scan.id),
            },
        )
        raise


def generate_browser_alerts(scan) -> None:
    if scan.organization is None:
        return

    browser_info = scan.browser_scan_info or {}
    if not browser_info.get("detected", False):
        return

    domain_obj = _get_domain_obj(scan)

    try:
        if _open_alert_exists(scan.organization, domain_obj, "malware_detected"):
            return

        try:
            with transaction.atomic():
                alert = Alert.objects.create(
                    organization=scan.organization,
                    domain=domain_obj,
                    scan=scan,
                    type="malware_detected",
                    severity="critical",
                    title=f"Browser-level malware detected on {scan.domain}",
                    description=f'Layer 2 browser scan intercepted {len(browser_info.get("malicious_requests", []))} malicious network requests.',
                )
                alert_id = str(alert.id)
                transaction.on_commit(lambda: _dispatch_alert_email(alert_id))
                try:
                    AuditLog.objects.create(
                        organization=scan.organization,
                        actor=None,
                        action="ALERT_GENERATED",
                        resource_type="Alert",
                        resource_id=alert_id,
                        changes={"type": "malware_detected", "scan_id": str(scan.id)},
                    )
                except ValidationError:
                    raise
                except Exception as audit_exc:
                    logger.error(
                        "AuditLog write failed for browser alert %s: %s",
                        alert_id,
                        audit_exc,
                        extra={
                            "org_id": str(scan.organization.id),
                            "alert_id": alert_id,
                            "scan_id": str(scan.id),
                        },
                    )
        except ValidationError:
            raise
        except Exception as e:
            logger.error(
                "generate_browser_alerts DB error for scan %s: %s",
                scan.id,
                e,
                extra={"org_id": str(scan.organization.id), "scan_id": str(scan.id)},
            )
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "generate_browser_alerts error for scan %s: %s",
            scan.id,
            e,
            exc_info=True,
            extra={
                "org_id": str(scan.organization.id) if scan.organization else "unknown",
                "scan_id": str(scan.id),
            },
        )


def _dispatch_slack(organization, scan_domain: str, alert) -> None:
    try:
        from apps.domains.models import Domain

        domain_obj = (
            Domain.objects.filter(
                organization=organization,
                domain=scan_domain,
                slack_webhook_url__isnull=False,
                deleted_at__isnull=True,
            )
            .exclude(slack_webhook_url="")
            .first()
        )

        if not domain_obj:
            return

        webhook_url = domain_obj.slack_webhook_url
        if not webhook_url.startswith(_SLACK_WEBHOOK_PREFIX):
            logger.warning(
                "_dispatch_slack: blocked invalid Slack webhook URL for org %s",
                organization.id,
                extra={"org_id": str(organization.id)},
            )
            return

        try:
            _validate_url_not_ssrf(webhook_url)
        except ValidationError:
            logger.warning(
                "_dispatch_slack: SSRF guard blocked URL for org %s",
                organization.id,
                extra={"org_id": str(organization.id)},
            )
            return

        import requests

        message = (
            f"*[{alert.severity.upper()}] {alert.title}*\n"
            f"Type: {alert.type}\nDomain: {scan_domain}"
        )
        response = requests.post(
            webhook_url,
            json={"text": message},
            timeout=5,
        )
        response.raise_for_status()
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "_dispatch_slack failed for org %s: %s",
            organization.id,
            e,
            extra={"org_id": str(organization.id)},
        )


def list_alerts(org, query_params: dict = None):
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    query_params = query_params or {}
    try:
        qs = Alert.objects.filter(
            organization=org,
            deleted_at__isnull=True,
        ).select_related("scan", "resolved_by", "domain", "domain__organization")

        is_resolved = query_params.get("is_resolved")
        if is_resolved is not None:
            qs = qs.filter(is_resolved=(is_resolved.lower() == "true"))

        severity = query_params.get("severity")
        valid_severities = {"critical", "high", "medium", "low"}
        if severity and severity in valid_severities:
            qs = qs.filter(severity=severity)

        return qs.order_by("-created_at")
    except (OperationalError, ProgrammingError) as e:
        logger.error("AlertService.list DB error: %s", e, extra={"org_id": str(org.id)})
        return Alert.objects.none()
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "AlertService.list unexpected error: %s",
            e,
            exc_info=True,
            extra={"org_id": str(org.id)},
        )
        raise


def resolve_alert(alert_id: str, org, user, note: str = "") -> Alert:
    if org is None:
        raise ValidationError({"detail": "Organization context required."})

    with transaction.atomic():
        try:
            alert = (
                Alert.objects.select_for_update()
                .filter(
                    organization=org,
                    deleted_at__isnull=True,
                )
                .get(pk=alert_id)
            )
        except Alert.DoesNotExist:
            raise NotFound("Alert not found.")
        except (OperationalError, ProgrammingError) as e:
            logger.error(
                "AlertService.resolve DB error: %s",
                e,
                extra={"org_id": str(org.id), "alert_id": str(alert_id)},
            )
            raise ValidationError({"detail": "Service unavailable."})

        if alert.is_resolved:
            return alert

        alert.is_resolved = True
        alert.resolved_by = user
        alert.resolved_note = note
        alert.resolved_at = timezone.now()
        alert.save(
            update_fields=[
                "is_resolved",
                "resolved_by",
                "resolved_note",
                "resolved_at",
                "updated_at",
            ]
        )
        try:
            AuditLog.objects.create(
                organization=org,
                actor=user,
                action="ALERT_RESOLVED",
                resource_type="Alert",
                resource_id=str(alert.id),
                changes={"resolved_note": note},
            )
        except ValidationError:
            raise
        except Exception as audit_exc:
            logger.error(
                "AuditLog write failed for resolve_alert %s: %s",
                alert.id,
                audit_exc,
                extra={"org_id": str(org.id), "alert_id": str(alert.id)},
            )

    return alert


def generate_agent_alerts(agent, result) -> int:
    org = agent.organization
    if org is None:
        return 0
    if not result.malware_found or not result.findings:
        return 0

    try:
        from apps.scans.models import Scan

        domain_obj = agent.domain
        if domain_obj is None:
            logger.warning(
                "generate_agent_alerts: agent %s has no domain, cannot create alerts",
                agent.pk,
                extra={"org_id": str(org.id), "agent_id": str(agent.pk)},
            )
            return 0

        scan = (
            Scan.objects.filter(
                organization=org,
                domain=domain_obj.domain,
            )
            .order_by("-created_at")
            .first()
        )
        if scan is None:
            logger.warning(
                "generate_agent_alerts: no Scan found for domain %s org %s — alerts skipped",
                domain_obj.domain,
                org.id,
                extra={"org_id": str(org.id), "agent_id": str(agent.pk)},
            )
            return 0

        if _open_alert_exists(org, domain_obj, "malware_detected"):
            return 0

        severity_map = {"high": "critical", "medium": "high", "low": "medium"}
        raw_severities = [f.get("severity", "high") for f in result.findings if isinstance(f, dict)]
        top_severity = "critical"
        for sev in ("high", "medium", "low"):
            if sev in raw_severities:
                top_severity = severity_map.get(sev, "critical")
                break

        file_count = len(result.findings)
        description = (
            f"Server agent detected malware in {file_count} file(s). "
            f"Findings: {', '.join(str(f.get('file', '')) for f in result.findings[:5] if isinstance(f, dict))}"
        )

        try:
            with transaction.atomic():
                alert = Alert.objects.create(
                    organization=org,
                    domain=domain_obj,
                    scan=scan,
                    type="malware_detected",
                    severity=top_severity,
                    title=f"Server-side malware detected on {domain_obj.domain}",
                    description=description,
                )
                alert_id = str(alert.id)
                transaction.on_commit(lambda: _dispatch_alert_email(alert_id))
                try:
                    AuditLog.objects.create(
                        organization=org,
                        actor=None,
                        action="AGENT_ALERT_GENERATED",
                        resource_type="Alert",
                        resource_id=alert_id,
                        changes={
                            "type": "malware_detected",
                            "agent_id": str(agent.pk),
                            "server_scan_result_id": str(result.pk),
                            "files_infected": result.files_infected,
                        },
                    )
                except ValidationError:
                    raise
                except Exception as audit_exc:
                    logger.error(
                        "AuditLog write failed for agent alert %s: %s",
                        alert_id,
                        audit_exc,
                        extra={"org_id": str(org.id)},
                    )
                return 1
        except ValidationError:
            raise
        except Exception as e:
            logger.error(
                "generate_agent_alerts DB error for agent %s: %s",
                agent.pk,
                e,
                extra={"org_id": str(org.id), "agent_id": str(agent.pk)},
            )
            return 0

    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "generate_agent_alerts unexpected error for agent %s: %s",
            agent.pk,
            e,
            exc_info=True,
            extra={"org_id": str(org.id)},
        )
        return 0


def bulk_resolve_alerts(org, user, ids: list) -> int:
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    if not ids:
        return 0
    if len(ids) > 100:
        raise ValidationError({"detail": "Cannot resolve more than 100 alerts at once."})

    try:
        with transaction.atomic():
            updated = Alert.objects.filter(
                organization=org,
                pk__in=ids,
                deleted_at__isnull=True,
                is_resolved=False,
            ).update(
                is_resolved=True,
                resolved_by=user,
                resolved_at=timezone.now(),
                updated_at=timezone.now(),
            )
            try:
                AuditLog.objects.create(
                    organization=org,
                    actor=user,
                    action="ALERTS_BULK_RESOLVED",
                    resource_type="Alert",
                    resource_id="bulk",
                    changes={"ids": [str(i) for i in ids], "resolved_count": updated},
                )
            except ValidationError:
                raise
            except Exception as audit_exc:
                logger.error(
                    "AuditLog write failed for bulk_resolve_alerts: %s",
                    audit_exc,
                    extra={"org_id": str(org.id), "resolved_count": updated},
                )

        return updated
    except (OperationalError, ProgrammingError) as e:
        logger.error("AlertService.bulk_resolve DB error: %s", e, extra={"org_id": str(org.id)})
        raise ValidationError({"detail": "Service unavailable."})
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "AlertService.bulk_resolve unexpected error: %s",
            e,
            exc_info=True,
            extra={"org_id": str(org.id)},
        )
        raise
