import logging
from datetime import datetime
from datetime import timezone as dt_timezone

logger = logging.getLogger(__name__)


def get_whois_info(domain: str) -> dict:
    result = {
        "registrar": None,
        "registrar_url": None,
        "creation_date": None,
        "expiration_date": None,
        "updated_date": None,
        "name_servers": [],
        "status": [],
        "registrant_name": None,
        "registrant_org": None,
        "registrant_country": None,
        "domain_age_days": None,
        "error": None,
    }

    try:
        import whois

        data = whois.whois(domain)

        result["registrar"] = getattr(data, "registrar", None)
        result["registrar_url"] = getattr(data, "registrar_url", None)
        result["registrant_name"] = getattr(data, "name", None)
        result["registrant_org"] = getattr(data, "org", None)
        result["registrant_country"] = getattr(data, "country", None)

        creation = getattr(data, "creation_date", None)
        if isinstance(creation, list):
            creation = creation[0]
        if isinstance(creation, datetime):
            result["creation_date"] = creation.strftime("%Y-%m-%dT%H:%M:%SZ")
            creation_utc = creation if creation.tzinfo else creation.replace(tzinfo=dt_timezone.utc)
            domain_age = (datetime.now(tz=dt_timezone.utc) - creation_utc).days
            result["domain_age_days"] = max(0, domain_age)

        expiration = getattr(data, "expiration_date", None)
        if isinstance(expiration, list):
            expiration = expiration[0]
        if isinstance(expiration, datetime):
            result["expiration_date"] = expiration.strftime("%Y-%m-%dT%H:%M:%SZ")

        updated = getattr(data, "updated_date", None)
        if isinstance(updated, list):
            updated = updated[0]
        if isinstance(updated, datetime):
            result["updated_date"] = updated.strftime("%Y-%m-%dT%H:%M:%SZ")

        ns = getattr(data, "name_servers", None) or []
        if isinstance(ns, str):
            ns = [ns]
        result["name_servers"] = [n.lower() for n in ns if n][:8]

        status_raw = getattr(data, "status", None) or []
        if isinstance(status_raw, str):
            status_raw = [status_raw]
        result["status"] = [str(s) for s in status_raw][:5]

    except ImportError:
        result["error"] = "python-whois library not installed"
    except Exception as e:
        logger.warning("WHOIS lookup error for %s: %s", domain, e, extra={"domain": domain})
        result["error"] = str(e)

    return result
