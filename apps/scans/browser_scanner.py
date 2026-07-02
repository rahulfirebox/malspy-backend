import ipaddress
import logging
import re
import socket
import time
from urllib.parse import urlparse

from django.core.cache import cache

_GOOGLE_REFERER_BASE = "https://www.google.com/search?q="

_LEGITIMATE_REDIRECT_PATTERNS = [
    re.compile(r"^www\."),
    re.compile(r"\.cloudfront\.net$"),
    re.compile(r"\.akamaihd\.net$"),
    re.compile(r"\.fastly\.net$"),
    re.compile(r"\.cloudflare\.com$"),
    re.compile(r"\.cdn\.ampproject\.org$"),
]


def _is_suspicious_redirect(from_domain: str, to_domain: str) -> bool:
    if not to_domain or not from_domain:
        return False

    if to_domain == from_domain:
        return False

    if to_domain == f"www.{from_domain}" or from_domain == f"www.{to_domain}":
        return False

    for pattern in _LEGITIMATE_REDIRECT_PATTERNS:
        if pattern.search(to_domain):
            return False
    return True


logger = logging.getLogger(__name__)

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return any(ip in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        return True


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except (ValueError, AttributeError) as exc:
        logger.debug("_extract_domain: parse error for url: %s", exc)
        return ""


def _is_request_ssrf_blocked(url: str) -> bool:
    try:
        host = urlparse(url).hostname
        if not host:
            return True
        resolved = socket.gethostbyname(host)
        return _is_private_ip(resolved)
    except Exception:
        return True


_BLOCKLIST_CACHE_KEY = "browser_blocklist_set"


def _load_blocklist_from_cache() -> set:
    cached = cache.get(_BLOCKLIST_CACHE_KEY)
    if cached is not None:
        return cached
    try:
        from .models import MalwareSignature

        blocked = set(
            MalwareSignature.objects.filter(layer="browser", is_active=True).values_list(
                "pattern", flat=True
            )
        )
        cache.set(_BLOCKLIST_CACHE_KEY, blocked, timeout=300)
        return blocked
    except Exception:
        return set()


def _check_domain_blocklist(domain: str, blocklist: set | None = None) -> bool:
    if blocklist is None:
        blocklist = _load_blocklist_from_cache()
    return domain in blocklist


class BrowserScanner:

    PAGE_LOAD_TIMEOUT = 30_000

    def run(self, url: str) -> dict:
        from playwright.sync_api import sync_playwright

        from .scanner import validate_url_for_server_fetch

        try:
            validate_url_for_server_fetch(url)
        except ValueError as e:
            logger.warning("BrowserScanner SSRF blocked for %s: %s", url, e, extra={"url": url})
            return {
                "detected": False,
                "page_load_ms": None,
                "total_requests_intercepted": 0,
                "malicious_requests": [],
                "redirects": [],
                "console_errors": [],
                "error": "Invalid scan target.",
            }

        scan_domain = _extract_domain(url)
        start = time.time()

        blocklist = _load_blocklist_from_cache()

        result = {
            "detected": False,
            "page_load_ms": None,
            "total_requests_intercepted": 0,
            "malicious_requests": [],
            "redirects": [],
            "console_errors": [],
            "error": None,
        }

        intercepted_requests: list[dict] = []
        page_src_scripts: set[str] = set()
        console_errors: list[dict] = []
        redirects: list[str] = []

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                context = browser.new_context(
                    extra_http_headers={
                        "Referer": f"{_GOOGLE_REFERER_BASE}{scan_domain}",
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                    }
                )
                page = context.new_page()

                def _route_handler(route):
                    req_url = route.request.url
                    if _is_request_ssrf_blocked(req_url):
                        logger.warning(
                            "BrowserScanner blocked private-IP request: %s",
                            req_url,
                            extra={"req_url": req_url},
                        )
                        route.abort()
                    else:
                        route.continue_()

                page.route("**", _route_handler)

                def on_request(req):
                    intercepted_requests.append(
                        {
                            "url": req.url,
                            "resource_type": req.resource_type,
                            "method": req.method,
                        }
                    )

                def on_console(msg):
                    if msg.type in ("error", "warning"):
                        console_errors.append({"type": msg.type, "text": msg.text})

                page.on("request", on_request)
                page.on("console", on_console)

                try:
                    page.goto(url, wait_until="networkidle", timeout=self.PAGE_LOAD_TIMEOUT)
                    final_url = page.url
                    final_domain = _extract_domain(final_url)
                    if final_domain and final_domain != scan_domain:
                        redirects.append(final_url)
                    for el in page.query_selector_all("script[src]"):
                        src = el.get_attribute("src")
                        if src:
                            page_src_scripts.add(src.split("?")[0])
                except Exception as exc:
                    logger.error(
                        "BrowserScanner error for %s: %s",
                        url,
                        exc,
                        exc_info=True,
                        extra={"url": url},
                    )
                    result["error"] = f"Browser scan failed: {type(exc).__name__}"
                    page.close()
                    browser.close()
                    return result

                elapsed = int((time.time() - start) * 1000)
                result["page_load_ms"] = elapsed
                result["total_requests_intercepted"] = len(intercepted_requests)
                result["redirects"] = redirects
                result["console_errors"] = console_errors[:20]

                malicious: list[dict] = []

                for req in intercepted_requests:
                    req_host = _extract_domain(req["url"])
                    resource_type = req["resource_type"]
                    req_url = req["url"]

                    if req_host and _check_domain_blocklist(req_host, blocklist):
                        if resource_type == "script":
                            malicious.append(
                                {
                                    "url": req_url,
                                    "type": resource_type,
                                    "triggered_by": "static_load",
                                    "finding": "BW-001",
                                    "name": "Cryptominer — Runtime Load",
                                    "severity": "critical",
                                }
                            )
                        elif resource_type in ("fetch", "xhr"):
                            malicious.append(
                                {
                                    "url": req_url,
                                    "type": resource_type,
                                    "triggered_by": "fetch",
                                    "finding": "BW-002",
                                    "name": "Data Exfiltration via Fetch",
                                    "severity": "high",
                                }
                            )
                        else:
                            malicious.append(
                                {
                                    "url": req_url,
                                    "type": resource_type,
                                    "triggered_by": "static_load",
                                    "finding": "BW-005",
                                    "name": "C2 Domain Contact",
                                    "severity": "critical",
                                }
                            )
                        continue

                    if resource_type == "script":
                        clean_url = req_url.split("?")[0]
                        if (
                            clean_url not in page_src_scripts
                            and req_host
                            and req_host != scan_domain
                        ):
                            malicious.append(
                                {
                                    "url": req_url,
                                    "type": resource_type,
                                    "triggered_by": "dynamic_inject",
                                    "finding": "BW-003",
                                    "name": "Dynamic Script Injection",
                                    "severity": "high",
                                }
                            )

                for redir_url in redirects:
                    redir_domain = _extract_domain(redir_url)
                    if _is_suspicious_redirect(scan_domain, redir_domain):
                        malicious.append(
                            {
                                "url": redir_url,
                                "type": "navigation",
                                "triggered_by": "redirect",
                                "finding": "BW-006",
                                "name": "Redirect to External Domain",
                                "severity": "medium",
                            }
                        )

                result["malicious_requests"] = malicious
                result["detected"] = len(malicious) > 0

                page.close()
                browser.close()

        except Exception as exc:
            logger.error(
                "BrowserScanner error for %s: %s",
                url,
                exc,
                exc_info=True,
                extra={"url": url},
            )
            result["error"] = f"Browser scan failed: {type(exc).__name__}"

        return result
