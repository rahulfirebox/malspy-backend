import logging
import socket
import ssl
from datetime import timezone as dt_timezone

from django.utils import timezone

logger = logging.getLogger(__name__)


def check_tls_direct(host: str, port: int = 443, timeout: int = 10) -> dict:
    result = {
        "connected": False,
        "tls_version": None,
        "cipher_suite": None,
        "cert_subject": None,
        "cert_issuer": None,
        "cert_issuer_org": None,
        "cert_serial": None,
        "cert_not_before": None,
        "cert_not_after": None,
        "cert_days_remaining": None,
        "cert_expired": None,
        "cert_expiring_soon": None,
        "san": [],
        "ocsp_stapling": False,
        "hsts": False,
        "hsts_max_age": None,
        "error": None,
    }

    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                result["connected"] = True
                result["tls_version"] = ssock.version()
                cipher = ssock.cipher()
                result["cipher_suite"] = cipher[0] if cipher else None

                cert = ssock.getpeercert()
                if cert:

                    subject = dict(x[0] for x in cert.get("subject", []))
                    result["cert_subject"] = subject.get("commonName")

                    issuer = dict(x[0] for x in cert.get("issuer", []))
                    result["cert_issuer"] = issuer.get("commonName")
                    result["cert_issuer_org"] = issuer.get("organizationName")

                    import ssl as ssl_module

                    not_before_str = cert.get("notBefore", "")
                    not_after_str = cert.get("notAfter", "")

                    if not_before_str:
                        try:
                            not_before = ssl_module.cert_time_to_seconds(not_before_str)
                            from datetime import datetime

                            result["cert_not_before"] = datetime.fromtimestamp(
                                not_before, tz=dt_timezone.utc
                            ).strftime("%Y-%m-%dT%H:%M:%SZ")
                        except Exception as exc:
                            logger.debug(
                                "cert_not_before parse failed for %s: %s",
                                host,
                                exc,
                                extra={"host": host},
                            )

                    if not_after_str:
                        try:
                            not_after_ts = ssl_module.cert_time_to_seconds(not_after_str)
                            from datetime import datetime

                            not_after_dt = datetime.fromtimestamp(not_after_ts, tz=dt_timezone.utc)
                            result["cert_not_after"] = not_after_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                            days_remaining = (not_after_dt - timezone.now()).days
                            result["cert_days_remaining"] = days_remaining
                            result["cert_expired"] = days_remaining < 0
                            result["cert_expiring_soon"] = 0 <= days_remaining <= 30
                        except Exception as exc:
                            logger.debug(
                                "cert_not_after parse failed for %s: %s",
                                host,
                                exc,
                                extra={"host": host},
                            )

                    san_list = []
                    for san_type, san_value in cert.get("subjectAltName", []):
                        if san_type == "DNS":
                            san_list.append(san_value)
                    result["san"] = san_list

    except ssl.SSLError as e:
        result["error"] = f"SSL error: {e}"
    except socket.timeout:
        result["error"] = "Connection timed out"
    except OSError as e:
        result["error"] = f"Connection error: {e}"
    except Exception as e:
        logger.error(
            "TLS check unexpected error for %s: %s",
            host,
            e,
            exc_info=True,
            extra={"host": host},
        )
        result["error"] = str(e)

    if result["connected"]:
        try:
            import requests

            from apps.scans.scanner import validate_url_for_server_fetch

            hsts_url = f"https://{host}"
            validate_url_for_server_fetch(hsts_url)
            resp = requests.get(hsts_url, timeout=5, allow_redirects=False)
            resp.raise_for_status()
            hsts_header = resp.headers.get("Strict-Transport-Security", "")
            if hsts_header:
                result["hsts"] = True
                for part in hsts_header.split(";"):
                    part = part.strip()
                    if part.lower().startswith("max-age="):
                        try:
                            result["hsts_max_age"] = int(part.split("=")[1])
                        except (ValueError, IndexError) as exc:
                            logger.debug(
                                "HSTS max-age parse failed for %s: %s",
                                host,
                                exc,
                                extra={"host": host},
                            )
        except ValueError as exc:

            logger.debug(
                "HSTS check skipped for %s (SSRF guard): %s",
                host,
                exc,
                extra={"host": host},
            )
        except Exception as exc:
            logger.debug(
                "HSTS check failed for %s: %s",
                host,
                exc,
                extra={"host": host},
            )

    return result
