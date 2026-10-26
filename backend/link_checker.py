"""Link check for reference-material candidates (Phase 8B, design 3-3). The server opens an address
an admin typed (or an AI suggested), so every step assumes the address is hostile.

A link passes only when all of these hold; the first failure ends the check with its code:
 1 format      https only, <= 2048 chars, no user info, port 443 only, no whitespace/backslash
 2 domain      the host equals an entry of data/allowed_domains.json (no wildcard, no sub-domain)
 3 address     every address DNS returns is public (loopback, private, link-local, reserved,
               multicast, IPv4-mapped/6to4/Teredo/NAT64 IPv6 are refused)
 4 connection  the TLS connection goes to the address that was checked, never to a second DNS
               answer (DNS rebinding); Host and SNI stay the original host name
 5 limits      3 s to connect, 8 s in total (DNS waits, every hop and every read count against it),
               only the first 128 KB of the body is read
 6 redirects   never followed automatically; at most 3 by hand and each hop repeats 1-5
 7 response    status 200 and Content-Type text/html
 8 duplicate   same normalized URL as a live candidate or a catalog document

The two outside-world functions, `resolve_host` (DNS, given the time it may take) and `fetch_head`
(the request), are passed in by argument so that tests replace them; nothing here logs a URL, a page or a title - only codes.
"""

import http.client
import ipaddress
import logging
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

from page_metadata import PageMetadata, extract_metadata
from resource_urls import allowed_domains, is_tracking_param, normalize_url

logger = logging.getLogger("pacemate.resources.check")

MAX_URL_CHARS = 2048
CONNECT_TIMEOUT_SECONDS = 3.0
TOTAL_TIMEOUT_SECONDS = 8.0
MAX_BODY_BYTES = 128 * 1024
MAX_REDIRECTS = 3
READ_CHUNK_BYTES = 8192
USER_AGENT = "PaceMateLinkCheck/1.0 (reference link review)"
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

# Codes of a failed check ("auto:<code>" on a rejected candidate).
BAD_URL = "bad_url"
NOT_ALLOWED_DOMAIN = "not_allowed_domain"
PRIVATE_ADDRESS = "private_address"
DNS_FAILED = "dns_failed"
TIMEOUT = "timeout"
TOO_LARGE = "too_large"
FETCH_FAILED = "fetch_failed"
BAD_REDIRECT = "bad_redirect"
BAD_STATUS = "bad_status"
BAD_TYPE = "bad_type"
EMPTY_BODY = "empty_body"
DUPLICATE = "duplicate"


class CheckRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class FetchError(Exception):
    """The request failed. `code` is timeout, too_large or fetch_failed (connection, TLS, protocol)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class FetchedPage:
    status: int
    headers: dict[str, str]  # lower-case names, first value
    body: bytes  # at most MAX_BODY_BYTES, empty for a redirect


@dataclass(frozen=True)
class LinkCheckResult:
    ok: bool
    code: Optional[str]
    url: str  # normalized address that was checked ("" when it could not be parsed)
    link: str = ""  # the cleaned address to keep (see ParsedUrl.link)
    final_url: Optional[str] = None  # after redirects, when different
    domain: Optional[str] = None
    source_name: Optional[str] = None
    metadata: Optional[PageMetadata] = None
    checks: dict[str, str] = field(default_factory=dict)  # stage -> "pass" | code | "skipped"


# --- 1 + 2: format and domain ---------------------------------------------------------------

@dataclass(frozen=True)
class ParsedUrl:
    host: str
    target: str  # path and query as sent on the request line
    normalized: str
    absolute: str  # https://host + target, used to resolve a relative redirect
    link: str  # the address to show and keep: no fragment, no tracking parameters, trailing '/' kept


def parse_url(raw: str) -> ParsedUrl:
    """Check 1 (format) and 2 (domain). Raises CheckRejected(bad_url | not_allowed_domain)."""
    if not isinstance(raw, str):
        raise CheckRejected(BAD_URL)
    url = raw.strip()
    if not url or len(url) > MAX_URL_CHARS:
        raise CheckRejected(BAD_URL)
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 or ch == "\\" for ch in url):
        raise CheckRejected(BAD_URL)
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise CheckRejected(BAD_URL)
    if parts.scheme.lower() != "https" or "@" in parts.netloc or port not in (None, 443):
        raise CheckRejected(BAD_URL)
    host = parts.hostname
    if not host:
        raise CheckRejected(BAD_URL)
    # allowed hosts are plain ASCII names, so a non-ASCII (unicode, look-alike) host is never one of them
    if not host.isascii() or host not in allowed_domains():
        raise CheckRejected(NOT_ALLOWED_DOMAIN)
    target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    absolute = f"https://{host}{target}"
    return ParsedUrl(host=host, target=target, normalized=normalize_url(absolute), absolute=absolute, link=clean_link(host, parts))


def clean_link(host: str, parts) -> str:
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not is_tracking_param(k)])
    return f"https://{host}{parts.path or '/'}" + (f"?{query}" if query else "")


# --- 3: addresses ---------------------------------------------------------------------------

_EXTRA_NON_PUBLIC_V6 = tuple(
    ipaddress.ip_network(n) for n in ("64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "2001::/32", "100::/64")
)


def is_public_ip(ip: "ipaddress.IPv4Address | ipaddress.IPv6Address") -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped  # ::ffff:127.0.0.1 is 127.0.0.1
        elif any(ip in net for net in _EXTRA_NON_PUBLIC_V6):
            return False
    return bool(
        ip.is_global
        and not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified)
    )


def _public_addresses(host: str, resolver: Callable[[str, float], list[str]], timeout: float) -> list[str]:
    """Check 3. Every address of the answer must be public; one private address refuses the host."""
    try:
        answers = list(resolver(host, timeout))
    except (TimeoutError, FutureTimeout):
        raise CheckRejected(TIMEOUT)
    except Exception:
        raise CheckRejected(DNS_FAILED)
    if not answers:
        raise CheckRejected(DNS_FAILED)
    addresses: list[str] = []
    for answer in answers:
        try:
            ip = ipaddress.ip_address(str(answer).split("%")[0])
        except ValueError:
            raise CheckRejected(PRIVATE_ADDRESS)  # an answer that is not an IP literal is not trusted
        if not is_public_ip(ip):
            raise CheckRejected(PRIVATE_ADDRESS)
        if str(answer) not in addresses:
            addresses.append(str(answer))
    return addresses


_dns_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="resource-dns")


def resolve_host(host: str, timeout: float = CONNECT_TIMEOUT_SECONDS) -> list[str]:
    """DNS answer (all addresses) of `host`, within `timeout` seconds."""
    future = _dns_pool.submit(socket.getaddrinfo, host, 443, 0, socket.SOCK_STREAM)
    try:
        infos = future.result(timeout=timeout)
    except FutureTimeout:
        future.cancel()  # a lookup still waiting for a free worker is dropped, so stuck lookups do not pile up work
        raise
    return [info[4][0] for info in infos]


# --- 4 + 5: the request ---------------------------------------------------------------------

class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connects to `ip` and nowhere else; the TLS name and the Host header stay `host`."""

    def __init__(self, host: str, ip: str, timeout: float, context: ssl.SSLContext) -> None:
        super().__init__(host, 443, timeout=timeout, context=context)
        self._pinned_ip = ip

    def connect(self) -> None:
        sock = socket.create_connection((self._pinned_ip, 443), timeout=self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _connect(host: str, ip: str, timeout: float) -> http.client.HTTPSConnection:
    return _PinnedHTTPSConnection(host, ip, timeout, ssl.create_default_context())


def fetch_head(
    host: str,
    ip: str,
    target: str,
    deadline: float,
    clock: Callable[[], float] = time.monotonic,
    connect: Callable[..., http.client.HTTPSConnection] = _connect,
) -> FetchedPage:
    """GET `target` from `ip` (a checked address of `host`). The only function that reaches the outside.

    The first 128 KB of the body are read and then reading stops; a redirect is returned as it is.
    `deadline` is an absolute `clock()` time that the connect, the headers and every read respect.
    """
    remaining = deadline - clock()
    if remaining <= 0:
        raise FetchError(TIMEOUT)
    conn = connect(host, ip, min(CONNECT_TIMEOUT_SECONDS, remaining))
    try:
        conn.request(
            "GET",
            target,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html", "Accept-Encoding": "identity", "Connection": "close"},
        )
        _set_socket_timeout(conn, deadline, clock)
        response = conn.getresponse()
        headers = {name.lower(): value for name, value in reversed(response.getheaders())}
        status = response.status
        body = b""
        if status == 200:
            chunks, size = [], 0
            while size < MAX_BODY_BYTES:
                _set_socket_timeout(conn, deadline, clock)
                chunk = response.read(min(READ_CHUNK_BYTES, MAX_BODY_BYTES - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            body = b"".join(chunks)
        return FetchedPage(status=status, headers=headers, body=body)
    except FetchError:
        raise
    except (TimeoutError, socket.timeout):
        raise FetchError(TIMEOUT)
    except http.client.LineTooLong:
        raise FetchError(TOO_LARGE)
    except (OSError, http.client.HTTPException, ssl.SSLError, ValueError):
        raise FetchError(FETCH_FAILED)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _set_socket_timeout(conn: http.client.HTTPSConnection, deadline: float, clock: Callable[[], float]) -> None:
    """Every blocking call may take only what is left of the total time; a drip-feeding server cannot stretch it."""
    remaining = deadline - clock()
    if remaining <= 0:
        raise FetchError(TIMEOUT)
    sock = getattr(conn, "sock", None)
    if sock is not None:
        sock.settimeout(remaining)


def _fetch_from_any(
    host: str, addresses: list[str], target: str, deadline: float, clock, fetcher: Callable[..., FetchedPage]
) -> FetchedPage:
    """The first checked address that answers; a timeout ends the check, a refused connection tries the next."""
    last = FETCH_FAILED
    for ip in addresses:
        try:
            return fetcher(host, ip, target, deadline, clock)
        except FetchError as exc:
            if exc.code in (TIMEOUT, TOO_LARGE):
                raise CheckRejected(exc.code)
            last = exc.code
    raise CheckRejected(last)


# --- 7: response ----------------------------------------------------------------------------

def _media_type(headers: dict[str, str]) -> str:
    return headers.get("content-type", "").split(";")[0].strip().lower()


def _assert_html_page(page: FetchedPage) -> None:
    if page.status != 200:
        raise CheckRejected(BAD_STATUS)
    if _media_type(page.headers) != "text/html" or page.headers.get("content-encoding", "identity").strip().lower() not in ("", "identity"):
        raise CheckRejected(BAD_TYPE)
    if not page.body.strip():
        raise CheckRejected(EMPTY_BODY)


# --- 8: duplicate ---------------------------------------------------------------------------

def is_known_url(normalized: str) -> bool:
    """Already a catalog document or a pending/approved candidate (a rejected candidate does not count)."""
    from resource_store import find_live_candidate_by_url
    from resources_catalog import load_catalog

    return any(normalize_url(doc["url"]) == normalized for doc in load_catalog()) or find_live_candidate_by_url(normalized) is not None


# --- the whole check ------------------------------------------------------------------------

def check_link(
    url: str,
    *,
    resolver: Callable[[str, float], list[str]] = resolve_host,
    fetcher: Callable[..., FetchedPage] = fetch_head,
    is_duplicate: Callable[[str], bool] = is_known_url,
    clock: Callable[[], float] = time.monotonic,
) -> LinkCheckResult:
    """Run checks 1-8 on `url`; never raises, never logs more than the result code."""
    checks: dict[str, str] = {}
    shown_url, shown_link, domain, final_url, metadata = "", "", None, None, None
    stage = "format"
    try:
        deadline = clock() + TOTAL_TIMEOUT_SECONDS
        current = parse_url(url)
        shown_url, shown_link, domain = current.normalized, current.link, current.host
        checks.update(format="pass", domain="pass")
        stage = "duplicate"
        if is_duplicate(current.normalized):
            raise CheckRejected(DUPLICATE)
        checks["duplicate"] = "pass"

        visited = {current.normalized}
        redirects = 0
        while True:
            stage = "address"
            left = deadline - clock()
            if left <= 0:
                raise CheckRejected(TIMEOUT)
            # the DNS wait counts against the same total as the request (and is capped like a connect)
            addresses = _public_addresses(current.host, resolver, min(CONNECT_TIMEOUT_SECONDS, left))
            if clock() >= deadline:
                raise CheckRejected(TIMEOUT)
            checks["address"] = "pass"
            stage = "fetch"
            page = _fetch_from_any(current.host, addresses, current.target, deadline, clock, fetcher)
            checks["fetch"] = "pass"
            if page.status not in _REDIRECT_STATUSES:
                break
            stage = "redirect"
            redirects += 1
            location = page.headers.get("location", "").strip()
            if not location:
                raise CheckRejected(BAD_STATUS)
            if redirects > MAX_REDIRECTS:
                raise CheckRejected(BAD_REDIRECT)
            try:
                current = parse_url(urljoin(current.absolute, location))  # every hop starts again at check 1
            except CheckRejected:
                raise CheckRejected(BAD_REDIRECT)
            if current.normalized in visited:
                raise CheckRejected(BAD_REDIRECT)
            visited.add(current.normalized)

        stage = "response"
        _assert_html_page(page)
        checks["response"] = "pass"
        if current.normalized != shown_url:
            final_url = current.normalized
            stage = "duplicate"
            if is_duplicate(final_url):
                raise CheckRejected(DUPLICATE)
        metadata = extract_metadata(page.body, page.headers.get("content-type", ""))
        result = LinkCheckResult(
            ok=True,
            code=None,
            url=shown_url,
            link=shown_link,
            final_url=final_url,
            domain=domain,
            source_name=allowed_domains()[domain],
            metadata=metadata,
            checks=checks,
        )
        logger.info("link check passed (redirects=%d)", redirects)
        return result
    except CheckRejected as rejected:
        checks[stage] = rejected.code
        logger.info("link check rejected (code=%s, stage=%s)", rejected.code, stage)
        return LinkCheckResult(
            ok=False, code=rejected.code, url=shown_url, link=shown_link, final_url=final_url, domain=domain, checks=checks
        )
