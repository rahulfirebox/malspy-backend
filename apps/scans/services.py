import logging

import requests
from django.conf import settings
from django.contrib.postgres.search import SearchVector
from django.core.cache import cache
from django.db import IntegrityError, OperationalError, ProgrammingError, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.exceptions import ResourceNotFound

from .models import Scan
from .scanner import extract_domain, validate_url_for_server_fetch

logger = logging.getLogger(__name__)

SUCURI_API_URL = getattr(settings, "SUCURI_API_URL", "https://sitecheck.sucuri.net/api/v3/")
SUCURI_TIMEOUT = getattr(settings, "SUCURI_API_TIMEOUT", 30)

_SCAN_PRO_TTL = 2592000
_SCAN_PUBLIC_TTL = 86400
_SCAN_FREE_TTL = 604800


def check_and_increment_scan_quota(org_id, domain=None, skip_increment: bool = False) -> None:
    from apps.accounts.models import Organization

    with transaction.atomic():
        try:
            org = (
                Organization.objects.select_for_update(of=("self",))
                .select_related("plan")
                .get(id=org_id)
            )
        except Organization.DoesNotExist:
            raise ResourceNotFound("Organization not found.")
        org.refresh_from_db()
        if domain:
            already_scanning = Scan.objects.filter(
                organization=org,
                domain=domain,
                status__in=["queued", "scanning"],
                deleted_at__isnull=True,
            ).exists()
            if already_scanning:
                raise ValidationError(
                    {
                        "code": "CONFLICT",
                        "detail": "This domain is already being scanned.",
                    }
                )
        if org.quota_reset_at is None:
            import calendar as _calendar

            from django.utils import timezone as _tz

            _now = _tz.now()
            _m = _now.month + 1
            _y = _now.year + (_m - 1) // 12
            _m = ((_m - 1) % 12) + 1
            _d = min(_now.day, _calendar.monthrange(_y, _m)[1])
            org.quota_reset_at = _now.replace(year=_y, month=_m, day=_d)
            Organization.objects.filter(id=org_id).update(
                quota_reset_at=org.quota_reset_at, updated_at=timezone.now()
            )

        if not skip_increment:
            if org.plan is None:
                raise ValidationError({"detail": "No active plan found."})
            if org.plan.scan_quota != -1 and org.scan_quota_used >= org.plan.scan_quota:
                raise ValidationError(
                    {
                        "code": "QUOTA_EXCEEDED",
                        "detail": "Monthly scan quota reached. Please upgrade.",
                    }
                )
            Organization.objects.filter(id=org_id).update(
                scan_quota_used=F("scan_quota_used") + 1, updated_at=timezone.now()
            )


def check_plan_feature(org, feature: str) -> None:
    if org.plan is None:
        raise ValidationError({"detail": "No active plan. Please subscribe to a plan."})
    if not getattr(org.plan, feature, False):
        raise ValidationError(
            {
                "code": "PLAN_REQUIRED",
                "detail": "Your plan does not support this feature. Upgrade required.",
            }
        )


def call_sucuri_api(domain: str) -> dict:
    try:
        response = requests.get(
            SUCURI_API_URL,
            params={"scan": domain},
            timeout=SUCURI_TIMEOUT,
            headers={"User-Agent": "SucuriClone/1.0"},
            allow_redirects=True,
        )
        response.raise_for_status()
        return response.json()
    except requests.Timeout:
        raise ValidationError({"detail": "External scan API timed out. Please retry."})
    except requests.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else 0
        if e.response is not None and 400 <= status_code < 500:
            logger.warning(
                "Sucuri API client error HTTP %s for %s: %s",
                status_code,
                domain,
                e,
                extra={"domain": domain, "status_code": status_code},
            )
            raise ValidationError({"detail": "External scan service rejected the request."})
        logger.error(
            "Sucuri API server error HTTP %s for %s: %s",
            status_code,
            domain,
            e,
            extra={"domain": domain, "status_code": status_code},
        )
        raise
    except requests.RequestException as e:
        logger.error("Sucuri API call failed for %s: %s", domain, e, extra={"domain": domain})
        raise ValidationError({"detail": "External scan service unavailable."})
    except ValueError as e:
        logger.error("Sucuri API invalid JSON for %s: %s", domain, e, extra={"domain": domain})
        raise ValidationError({"detail": "External scan service returned invalid data."})


def parse_sucuri_response(raw: dict, domain: str) -> dict:
    site_info = {}
    tls_info = {}
    recommendations = {}
    blacklist_info = {
        "listed": False,
        "data_source": "sucuri_sitecheck_v3",
        "providers": {},
    }
    links_info = {}
    ratings_info = {}
    software_info = {}
    overall_rating = "B"

    try:

        site_raw = raw.get("site", {})
        site_info = {
            "input": site_raw.get("input", ""),
            "domain": site_raw.get("domain", domain),
            "final_url": site_raw.get("final_url", ""),
            "ip": site_raw.get("ip", []),
            "redirects_to": site_raw.get("redirects_to", []),
            "cdn": site_raw.get("cdn", []),
            "running_on": site_raw.get("running_on", []),
        }

        software_raw = raw.get("software", {})
        software_info = {
            "cms": software_raw.get("cms", []),
            "server": software_raw.get("server", []),
            "language": software_raw.get("language"),
            "plugins": software_raw.get("plugins", []),
        }

        tls_raw = raw.get("tls", {})
        tls_info = {
            "cert_expires": tls_raw.get("cert_expires"),
            "cert_issuer": tls_raw.get("cert_issuer"),
            "cert_authority": tls_raw.get("cert_authority"),
        }

        links_raw = raw.get("links", {})
        links_info = {
            "iframes": links_raw.get("iframes", []),
            "js_external": links_raw.get("js_external", []),
            "js_local": links_raw.get("js_local", []),
            "urls": links_raw.get("urls", []),
        }

        ratings_raw = raw.get("ratings", {})
        ratings_info = {
            "total": ratings_raw.get("total", {}),
            "security": ratings_raw.get("security", {}),
            "domain": ratings_raw.get("domain", {}),
            "tls": ratings_raw.get("tls", {}),
        }
        overall_rating = ratings_info.get("total", {}).get("rating", "B") or "B"

        recommendations = raw.get("recommendations", {})

        blacklist_raw = raw.get("blacklist", {})
        providers = {}
        for provider_key in [
            "google_safe_browsing",
            "mcafee",
            "phishtank",
            "norton_safe_web",
            "yandex",
            "opera",
            "spamhaus",
        ]:
            providers[provider_key] = bool(blacklist_raw.get(provider_key, False))
        blacklist_info = {
            "listed": any(providers.values()),
            "data_source": "sucuri_sitecheck_v3",
            "providers": providers,
        }

    except ValidationError:
        raise
    except Exception as exc:
        logger.error(
            "parse_sucuri_response: unexpected error for %s: %s",
            domain,
            exc,
            exc_info=True,
            extra={"domain": domain},
        )
        raise

    return {
        "site_info": site_info,
        "software_info": software_info,
        "tls_info": tls_info,
        "links_info": links_info,
        "ratings_info": ratings_info,
        "recommendations": recommendations,
        "blacklist_info": blacklist_info,
        "overall_rating": overall_rating,
        "blacklisted": blacklist_info.get("listed", False),
    }


def _get_cache_key(domain: str, plan_slug: str = "public") -> str:
    return f"sucuri_api:{plan_slug}:{domain}"


def _get_cache_ttl(plan_slug: str) -> int:
    if plan_slug == "enterprise":
        return 0
    if plan_slug == "pro":
        return getattr(settings, "SCAN_CACHE_TTL_PRO", _SCAN_PRO_TTL)
    if plan_slug == "public":
        return getattr(settings, "SCAN_CACHE_TTL_PUBLIC", _SCAN_PUBLIC_TTL)
    return getattr(settings, "SCAN_CACHE_TTL_FREE", _SCAN_FREE_TTL)


def _get_cached_result(domain: str, plan_slug: str) -> dict | None:
    if plan_slug == "enterprise":
        return None
    key = _get_cache_key(domain, plan_slug)
    return cache.get(key)


def _set_cached_result(domain: str, plan_slug: str, result: dict) -> None:
    ttl = _get_cache_ttl(plan_slug)
    if ttl > 0:
        key = _get_cache_key(domain, plan_slug)
        lock_key = f"scan_cache_lock:{key}"
        if cache.add(lock_key, 1, timeout=30):
            try:
                cache.set(key, result, ttl)
            finally:
                cache.delete(lock_key)


def _normalize_url_scheme(url: str) -> str:
    url = url.strip()
    if url.startswith("http://"):
        url = "https://" + url[7:]
    elif not url.startswith("https://"):
        url = "https://" + url
    return url


def create_public_scan(url: str) -> Scan:

    try:
        validate_url_for_server_fetch(url)
    except ValueError as e:
        logger.warning("validate_url_for_server_fetch failed (public): %s", e, extra={"url": url})
        raise ValidationError({"url": ["Invalid URL provided."]})

    domain = extract_domain(url)

    cached = _get_cached_result(domain, "public")

    if not cached:
        in_flight = Scan.objects.filter(
            domain=domain,
            is_public=True,
            status__in=["queued", "scanning"],
            deleted_at__isnull=True,
        ).first()
        if in_flight is not None:
            return in_flight

    if cached:

        scan = Scan.objects.create(
            url=url,
            domain=domain,
            is_public=True,
            organization=None,
            created_by=None,
            status="completed",
            was_cached=True,
            notify_email=False,
            site_info=cached.get("site_info"),
            tls_info=cached.get("tls_info"),
            recommendations=cached.get("recommendations"),
            blacklist_info=cached.get("blacklist_info"),
            links_info=cached.get("links_info"),
            ratings_info=cached.get("ratings_info"),
            software_info=cached.get("software_info"),
            malware_info=cached.get("malware_info"),
            overall_rating=cached.get("overall_rating", "B"),
            blacklisted=cached.get("blacklisted", False),
            malware_detected=cached.get("malware_detected", False),
            sucuri_raw=cached.get("sucuri_raw"),
            completed_at=timezone.now(),
        )
        try:
            from apps.core.models import AuditLog

            AuditLog.objects.create(
                organization=None,
                actor=None,
                action="PUBLIC_SCAN_CREATED",
                resource_type="Scan",
                resource_id=str(scan.id),
                changes={"url": url, "was_cached": True},
            )
        except ValidationError:
            raise
        except Exception as e:
            logger.error(
                "AuditLog write failed on public scan create %s: %s",
                scan.id,
                e,
                extra={"scan_id": str(scan.id)},
            )
        return scan

    with transaction.atomic():
        scan = Scan.objects.create(
            url=url,
            domain=domain,
            is_public=True,
            organization=None,
            created_by=None,
            status="queued",
            was_cached=False,
            notify_email=False,
        )
        scan_id = str(scan.id)
        transaction.on_commit(lambda: _trigger_scan_task(scan_id))

    try:
        from apps.core.models import AuditLog

        AuditLog.objects.create(
            organization=None,
            actor=None,
            action="PUBLIC_SCAN_CREATED",
            resource_type="Scan",
            resource_id=str(scan.id),
            changes={"url": url, "was_cached": False},
        )
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "AuditLog write failed on public scan create %s: %s",
            scan.id,
            e,
            extra={"scan_id": str(scan.id)},
        )

    return scan


def _write_scan_audit_log(scan, org, user) -> None:
    try:
        from apps.core.models import AuditLog

        AuditLog.objects.create(
            organization=org,
            actor=user,
            action="CREATE",
            resource_type="Scan",
            resource_id=str(scan.id),
            changes={"url": scan.url, "domain": scan.domain},
        )
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "AuditLog write failed on scan create %s: %s",
            scan.id,
            e,
            extra={"scan_id": str(scan.id)},
        )


def _trigger_scan_task(scan_id: str) -> None:
    from .tasks import trigger_scan

    try:
        trigger_scan.delay(scan_id)
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "Celery broker unavailable, could not queue scan %s: %s",
            scan_id,
            e,
            extra={"scan_id": scan_id},
        )
        Scan.objects.filter(pk=scan_id).update(status="failed", updated_at=timezone.now())


def create_scan(data: dict, org, user, is_scheduled: bool = False) -> Scan:
    if org is None:
        raise ValidationError({"detail": "Organization context required."})

    url = _normalize_url_scheme(data.get("url", "").strip())
    if not url:
        raise ValidationError({"url": ["URL is required."]})

    try:
        validate_url_for_server_fetch(url)
    except ValueError as e:
        logger.warning("validate_url_for_server_fetch failed: %s", e, extra={"url": url})
        raise ValidationError({"url": ["Invalid URL provided."]})

    domain = extract_domain(url)
    notify_email = data.get("notify_email", True)

    plan_slug = org.plan.slug if org.plan else "free"

    force_fresh = data.get("force_fresh", False)
    cached = None if force_fresh else _get_cached_result(domain, plan_slug)

    if cached:
        try:
            with transaction.atomic():
                check_and_increment_scan_quota(org.id, domain=domain, skip_increment=is_scheduled)
                scan = Scan.objects.create(
                    url=url,
                    domain=domain,
                    organization=org,
                    created_by=user,
                    status="completed",
                    was_cached=True,
                    notify_email=notify_email,
                    site_info=cached.get("site_info"),
                    tls_info=cached.get("tls_info"),
                    recommendations=cached.get("recommendations"),
                    blacklist_info=cached.get("blacklist_info"),
                    links_info=cached.get("links_info"),
                    ratings_info=cached.get("ratings_info"),
                    software_info=cached.get("software_info"),
                    malware_info=cached.get("malware_info"),
                    overall_rating=cached.get("overall_rating", "B"),
                    blacklisted=cached.get("blacklisted", False),
                    malware_detected=cached.get("malware_detected", False),
                    sucuri_raw=cached.get("sucuri_raw"),
                    completed_at=timezone.now(),
                )
        except IntegrityError as exc:
            logger.warning("create_scan (cached): IntegrityError: %s", exc, extra={"url": url})
            raise ValidationError({"detail": "Scan record could not be created. Please retry."})
        _write_scan_audit_log(scan, org, user)
        return scan

    try:
        with transaction.atomic():
            check_and_increment_scan_quota(org.id, domain=domain, skip_increment=is_scheduled)
            scan = Scan.objects.create(
                url=url,
                domain=domain,
                organization=org,
                created_by=user,
                status="queued",
                was_cached=False,
                notify_email=notify_email,
            )
            scan_id = str(scan.id)
            transaction.on_commit(lambda: _trigger_scan_task(scan_id))
    except IntegrityError as exc:
        logger.warning("create_scan: IntegrityError: %s", exc, extra={"url": url})
        raise ValidationError({"detail": "Scan record could not be created. Please retry."})

    _write_scan_audit_log(scan, org, user)
    return scan


def rescan(original_scan_id: str, org, user) -> Scan:
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    try:
        original = Scan.objects.filter(
            organization=org,
            deleted_at__isnull=True,
        ).get(pk=original_scan_id)
    except Scan.DoesNotExist:
        raise NotFound({"detail": "Original scan not found."})
    except (OperationalError, ProgrammingError) as e:
        logger.error("rescan DB error: %s", e, extra={"scan_id": original_scan_id})
        raise ValidationError({"detail": "Service unavailable."})

    check_and_increment_scan_quota(org.id, domain=original.domain)

    try:
        with transaction.atomic():
            new_scan = Scan.objects.create(
                url=original.url,
                domain=original.domain,
                organization=org,
                created_by=user,
                status="queued",
                was_cached=False,
                notify_email=original.notify_email,
                parent_scan_id=original.id,
            )
            scan_id = str(new_scan.id)
            transaction.on_commit(lambda: _trigger_scan_task(scan_id))
    except IntegrityError as exc:
        logger.warning("rescan: IntegrityError: %s", exc, extra={"scan_id": original_scan_id})
        raise ValidationError({"detail": "Rescan record could not be created. Please retry."})

    _write_scan_audit_log(new_scan, org, user)
    return new_scan


def list_scans(org, query_params: dict) -> tuple:
    if org is None:
        raise ValidationError({"detail": "Organization context required."})

    try:
        qs = Scan.objects.filter(
            organization=org,
            deleted_at__isnull=True,
        ).select_related("created_by", "organization")

        q = query_params.get("q")
        if q:
            qs = qs.annotate(search=SearchVector("domain", "url")).filter(search=q)

        status_filter = query_params.get("status")
        valid_statuses = {"queued", "scanning", "completed", "failed"}
        if status_filter and status_filter in valid_statuses:
            qs = qs.filter(status=status_filter)

        rating_filter = query_params.get("rating")
        valid_ratings = {"A", "B", "C", "D", "E", "F"}
        if rating_filter and rating_filter in valid_ratings:
            qs = qs.filter(overall_rating=rating_filter)

        ordering = query_params.get("ordering", "-created_at")
        allowed_orderings = [
            "-created_at",
            "created_at",
            "domain",
            "-domain",
            "overall_rating",
        ]
        if ordering not in allowed_orderings:
            ordering = "-created_at"
        qs = qs.order_by(ordering)

        return qs
    except (OperationalError, ProgrammingError) as exc:
        logger.error(
            "list_scans DB error: %s",
            exc,
            extra={},
        )
        raise ValidationError({"detail": "Database temporarily unavailable."})
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "list_scans unexpected error: %s",
            e,
            exc_info=True,
            extra={},
        )
        raise


def get_scan(scan_id: str, org) -> Scan:
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    try:
        return (
            Scan.objects.filter(
                organization=org,
                deleted_at__isnull=True,
            )
            .select_related("created_by", "organization")
            .get(pk=scan_id)
        )
    except Scan.DoesNotExist:
        raise NotFound({"detail": "Scan not found."})
    except (OperationalError, ProgrammingError) as e:
        logger.error(
            "get_scan DB error: %s",
            e,
            extra={},
        )
        raise ValidationError({"detail": "Service unavailable."})


def delete_scan(scan_id: str, org, user) -> None:
    if org is None:
        raise ValidationError({"detail": "Organization context required."})
    try:
        scan = Scan.objects.filter(
            organization=org,
            deleted_at__isnull=True,
        ).get(pk=scan_id)
    except Scan.DoesNotExist:
        raise NotFound({"detail": "Scan not found."})
    except (OperationalError, ProgrammingError) as e:
        logger.error(
            "delete_scan DB error: %s",
            e,
            extra={"scan_id": scan_id, "org_id": str(org.id) if org else None},
        )
        raise ValidationError({"detail": "Service unavailable."})

    scan_domain = scan.domain
    plan_slug = org.plan.slug if org.plan else "free"
    scan.soft_delete()
    cache.delete(f"scan:domain:{scan_domain}:latest")
    for slug in (plan_slug, "public", "free", "pro", "enterprise"):
        cache.delete(_get_cache_key(scan_domain, slug))

    try:
        with transaction.atomic():
            from apps.core.models import AuditLog

            AuditLog.objects.create(
                organization=org,
                actor=user,
                action="delete",
                resource_type="scan",
                resource_id=str(scan_id),
            )
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "AuditLog write failed on scan delete: %s",
            e,
            extra={"scan_id": str(scan_id)},
        )


def get_scan_status(scan_id: str, user=None):
    try:
        if user and user.is_authenticated:
            scan = (
                Scan.objects.select_related("organization", "created_by")
                .filter(
                    organization=user.organization,
                    pk=scan_id,
                    deleted_at__isnull=True,
                )
                .first()
            )
            if scan is None:
                scan = (
                    Scan.objects.select_related("organization", "created_by")
                    .filter(pk=scan_id, is_public=True, deleted_at__isnull=True)
                    .first()
                )
        else:
            scan = (
                Scan.objects.select_related("organization", "created_by")
                .filter(pk=scan_id, is_public=True, deleted_at__isnull=True)
                .first()
            )
        return scan
    except (OperationalError, ProgrammingError) as exc:
        logger.error("get_scan_status DB error: %s", exc, extra={"scan_id": str(scan_id)})
        raise ValidationError({"detail": "Service unavailable."})
    except ValidationError:
        raise
    except Exception as exc:
        logger.error(
            "get_scan_status unexpected error: %s",
            exc,
            exc_info=True,
            extra={"scan_id": str(scan_id)},
        )
        raise


def get_public_scan_detail(scan_id: str):
    try:

        return Scan.objects.filter(pk=scan_id, is_public=True, status="completed").first()
    except (OperationalError, ProgrammingError) as exc:
        logger.error("get_public_scan_detail DB error: %s", exc, extra={"scan_id": str(scan_id)})
        raise ValidationError({"detail": "Service unavailable."})
    except ValidationError:
        raise
    except Exception as exc:
        logger.error(
            "get_public_scan_detail unexpected error: %s",
            exc,
            exc_info=True,
            extra={"scan_id": str(scan_id)},
        )
        raise


def get_dashboard_analytics(org):
    from django.db.models import Count, Q

    from apps.alerts.models import Alert

    scan_stats = Scan.objects.filter(organization=org, deleted_at__isnull=True).aggregate(
        total_scans=Count("id"),
        clean_scans=Count(
            "id",
            filter=Q(status="completed", malware_detected=False, blacklisted=False),
        ),
        issues_found=Count(
            "id",
            filter=Q(status="completed") & (Q(malware_detected=True) | Q(blacklisted=True)),
        ),
        malware_detected_count=Count("id", filter=Q(malware_detected=True)),
        blacklisted_count=Count("id", filter=Q(blacklisted=True)),
    )
    active_alerts = Alert.objects.filter(organization=org, is_resolved=False).count()
    rating_dist_qs = list(
        Scan.objects.filter(organization=org, status="completed", deleted_at__isnull=True)
        .values("overall_rating")
        .annotate(count=Count("id", distinct=True))
    )
    rating_distribution = {
        r["overall_rating"]: r["count"] for r in rating_dist_qs if r["overall_rating"]
    }
    plan = org.plan
    return {
        "total_scans": scan_stats["total_scans"],
        "clean_scans": scan_stats["clean_scans"],
        "issues_found": scan_stats["issues_found"],
        "active_alerts": active_alerts,
        "malware_detected_count": scan_stats["malware_detected_count"],
        "blacklisted_count": scan_stats["blacklisted_count"],
        "open_alerts_count": active_alerts,
        "rating_distribution": rating_distribution,
        "scans_over_time": [],
        "top_domains_by_scans": [],
        "quota_used": org.scan_quota_used,
        "quota_limit": plan.scan_quota if plan else 0,
    }


def build_pdf_report(scan) -> "bytes | None":
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError:
        logger.error(
            "build_pdf_report: reportlab not installed",
            extra={"scan_id": str(scan.id) if scan else None},
        )
        return None
    import io

    try:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = [
            Paragraph(f"Security Report: {scan.domain}", styles["Title"]),
            Spacer(1, 12),
            Paragraph(f"Rating: {scan.overall_rating or 'N/A'}", styles["Normal"]),
            Paragraph(f"Malware: {'Yes' if scan.malware_detected else 'No'}", styles["Normal"]),
            Spacer(1, 12),
        ]
        for rec in (scan.recommendations or [])[:20]:
            label = rec.get("label") or rec.get("title") or str(rec)
            elements.append(Paragraph(f"- {label}", styles["Normal"]))
        doc.build(elements)
        return buf.getvalue()
    except OperationalError:
        raise
    except ValidationError:
        raise
    except Exception as e:
        logger.error(
            "build_pdf_report failed for %s: %s",
            scan.id,
            e,
            exc_info=True,
            extra={"scan_id": str(scan.id)},
        )
        return None
