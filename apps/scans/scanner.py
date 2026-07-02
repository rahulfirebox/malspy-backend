import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


SCAN_MAX_RESPONSE_BYTES = getattr(settings, "SCAN_MAX_RESPONSE_BYTES", 5 * 1024 * 1024)


STATIC_SIGNATURES = [
    {
        "id": "MW-001",
        "name": "JavaScript Eval Obfuscation",
        "severity": "high",
        "type": "js_obfuscation",
        "pattern": re.compile(r"eval\(unescape\(", re.IGNORECASE),
        "source": "html_source",
    },
    {
        "id": "MW-002",
        "name": "atob Large Payload Obfuscation",
        "severity": "high",
        "type": "js_obfuscation",
        "pattern": re.compile(r"atob\(['\"][A-Za-z0-9+/]{100,}", re.IGNORECASE),
        "source": "html_source",
    },
    {
        "id": "MW-005",
        "name": "SEO Spam Injection",
        "severity": "medium",
        "type": "seo_spam",
        "pattern": re.compile(
            r"(buy\s+cheap\s+viagra|cialis\s+online|casino\s+online|online\s+gambling|cheap\s+meds)",
            re.IGNORECASE,
        ),
        "source": "html_source",
    },
    {
        "id": "MW-006",
        "name": "WordPress Pharma Hack",
        "severity": "high",
        "type": "wp_pharma",
        "pattern": re.compile(
            r'(\/\*.*?\*\/\s*)?header\s*\(\s*["\']Location.*?pharma',
            re.IGNORECASE | re.DOTALL,
        ),
        "source": "html_source",
    },
    {
        "id": "MW-007",
        "name": "Suspicious JS Redirect",
        "severity": "critical",
        "type": "js_redirect",
        "pattern": re.compile(r"document\.location\s*=\s*atob\(", re.IGNORECASE),
        "source": "html_source",
    },
]


BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def validate_url_for_server_fetch(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https allowed, got: {parsed.scheme}")
    host = parsed.hostname
    if not host:
        raise ValueError("Missing host in URL.")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve host: {host}")
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        for net in BLOCKED_NETWORKS:
            if addr in net:
                raise ValueError(f"SSRF blocked — IP {addr} is in private range {net}.")
    return url


def extract_domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.hostname or url


def _load_active_signatures() -> list[dict]:

    cache_key = "static_signatures_compiled"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        from apps.scans.models import MalwareSignature

        db_sigs = list(
            MalwareSignature.objects.filter(layer="static", is_active=True).values(
                "signature_id", "name", "severity", "type", "pattern"
            )
        )
        if db_sigs:
            compiled = []
            for row in db_sigs:
                try:
                    compiled.append(
                        {
                            "id": row["signature_id"],
                            "name": row["name"],
                            "severity": row["severity"],
                            "type": row["type"],
                            "pattern": re.compile(row["pattern"], re.IGNORECASE),
                            "source": "html_source",
                        }
                    )
                except re.error as exc:
                    logger.warning(
                        "Invalid regex for sig %s: %s",
                        row["signature_id"],
                        exc,
                        extra={"signature_id": row["signature_id"]},
                    )
            if compiled:
                cache.set(cache_key, compiled, timeout=300)
                return compiled
    except Exception as exc:
        logger.error(
            "DB signature load failed: %s",
            exc,
            exc_info=True,
            extra={"cache_key": cache_key},
        )
        raise

    return STATIC_SIGNATURES


def _fetch_html(url: str, timeout: int = 15) -> tuple[str, int]:
    headers = {"User-Agent": "Mozilla/5.0 SucuriScanner/1.0"}
    try:
        resp = requests.get(
            url, timeout=timeout, allow_redirects=True, headers=headers, stream=True
        )
        resp.raise_for_status()

        chunks = []
        total = 0
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                total += len(chunk)
                if total > SCAN_MAX_RESPONSE_BYTES:
                    logger.warning(
                        "Response too large for %s, truncating at 5 MB",
                        url,
                        extra={"url": url},
                    )
                    break
                chunks.append(chunk)

        raw_bytes = b"".join(chunks)
        encoding = resp.encoding or "utf-8"
        if encoding.lower() in ("", "utf-8"):
            try:
                import chardet

                detected = chardet.detect(raw_bytes)
                if detected.get("confidence", 0) > 0.7:
                    encoding = detected["encoding"] or "utf-8"
            except ImportError:
                logger.debug(
                    "chardet not installed; skipping confidence-based encoding detection", extra={}
                )
        try:
            text = raw_bytes.decode(encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            text = raw_bytes.decode("utf-8", errors="replace")

        return text, total

    except requests.Timeout:
        logger.warning("Fetch timeout for %s", url, extra={"url": url})
        return "", 0
    except requests.HTTPError as e:
        logger.warning("HTTP error for %s: %s", url, e, extra={"url": url})
        return "", 0
    except requests.RequestException as e:
        logger.warning("Fetch error for %s: %s", url, e, extra={"url": url})
        return "", 0


def _check_domain_blocklist(domain: str) -> bool:
    malicious = getattr(settings, "MALICIOUS_DOMAINS", [])
    domain = domain.lower().strip()
    for blocked in malicious:
        if domain == blocked or domain.endswith("." + blocked):
            return True
    return False


def _find_hidden_iframes(soup: BeautifulSoup) -> list[dict]:
    findings = []
    for iframe in soup.find_all("iframe"):
        style = iframe.get("style", "")
        width = iframe.get("width", "")
        height = iframe.get("height", "")
        src = iframe.get("src", "")

        is_hidden = (
            "display:none" in style.replace(" ", "")
            or "display: none" in style
            or width in ("0", "0px")
            or height in ("0", "0px")
        )
        if is_hidden and src:
            findings.append(
                {
                    "signature_id": "MW-004",
                    "name": "Hidden iFrame",
                    "severity": "high",
                    "type": "hidden_iframe",
                    "source": "html_dom",
                    "source_url": src,
                    "matched_snippet": str(iframe)[:200],
                }
            )
    return findings


def _check_external_scripts(soup: BeautifulSoup, page_url: str) -> list[dict]:
    findings = []
    page_host = extract_domain(page_url)
    for script in soup.find_all("script", src=True):
        src = script.get("src", "")
        if not src or src.startswith("/") or src.startswith("#"):
            continue
        script_parsed = urlparse(src if "://" in src else f"https:{src}")
        script_host = script_parsed.hostname or ""
        if script_host and script_host != page_host:
            if _check_domain_blocklist(script_host):
                findings.append(
                    {
                        "signature_id": "MW-008",
                        "name": "Malicious External JS Domain",
                        "severity": "critical",
                        "type": "malicious_script",
                        "source": "html_source",
                        "source_url": src,
                        "matched_snippet": f'<script src="{src}">',
                    }
                )
    return findings


def _check_script_content(url: str, content: str) -> list[dict]:
    findings = []
    for sig in _load_active_signatures():
        match = sig["pattern"].search(content)
        if match:
            snippet = content[max(0, match.start() - 30) : match.end() + 50]
            findings.append(
                {
                    "signature_id": sig["id"],
                    "name": sig["name"],
                    "severity": sig["severity"],
                    "type": sig["type"],
                    "source": sig["source"],
                    "source_url": url,
                    "matched_snippet": snippet[:300],
                }
            )
    return findings


def run_layer1_scan(url: str) -> dict:
    findings = []
    scanned_files = [url]
    scanned_bytes = 0
    error = None

    try:
        html, byte_count = _fetch_html(url)
        scanned_bytes += byte_count

        if html:

            findings.extend(_check_script_content(url, html))

            soup = BeautifulSoup(html, "lxml")

            findings.extend(_find_hidden_iframes(soup))

            findings.extend(_check_external_scripts(soup, url))

            page_host = extract_domain(url)
            external_js_urls = []
            for script in soup.find_all("script", src=True):
                src = script.get("src", "")
                if not src or src.startswith("/") or src.startswith("#"):
                    continue
                full_src = src if "://" in src else f"https:{src}"
                js_host = extract_domain(full_src)
                if js_host and js_host != page_host:
                    external_js_urls.append(full_src)
                if len(external_js_urls) >= 5:
                    break

            for js_url in external_js_urls:
                try:
                    validate_url_for_server_fetch(js_url)
                    js_content, js_bytes = _fetch_html(js_url, timeout=10)
                    scanned_bytes += js_bytes
                    scanned_files.append(js_url)
                    if js_content:
                        js_findings = _check_script_content(js_url, js_content)
                        findings.extend(js_findings)
                except (ValueError, Exception) as e:
                    logger.debug("Skipping JS file %s: %s", js_url, e, extra={"js_url": js_url})

    except Exception as e:
        logger.error("Scanner error for domain %s: %s", url, e, exc_info=True, extra={"url": url})
        error = "Scan analysis failed. Please try again."

    return {
        "detected": len(findings) > 0,
        "scanned_bytes": scanned_bytes,
        "scanned_files": scanned_files,
        "findings": findings,
        "error": error,
    }
