"""Phase 8B step B: the link check (SSRF defence) and the page metadata reader.

No test reaches the network: DNS and the request are fakes passed into `check_link`, and the
real request code is driven through a fake connection."""

import http.client
import logging
import socket
import ssl
import time

import pytest

import link_checker
import resource_store
from link_checker import (
    BAD_REDIRECT,
    BAD_STATUS,
    BAD_TYPE,
    BAD_URL,
    DNS_FAILED,
    DUPLICATE,
    EMPTY_BODY,
    FETCH_FAILED,
    NOT_ALLOWED_DOMAIN,
    PRIVATE_ADDRESS,
    TIMEOUT,
    TOO_LARGE,
    FetchedPage,
    FetchError,
    check_link,
    fetch_head,
    parse_url,
)
from page_metadata import DESCRIPTION_MAX_CHARS, TITLE_MAX_CHARS, clean_text, extract_metadata
from resource_urls import allowed_domains, normalize_url

PUBLIC = "93.184.216.34"
HTML = b"<html><head><title>Python Tutorial</title><meta name='description' content='Learn Python'></head><body>x</body></html>"
OK_HEADERS = {"content-type": "text/html; charset=utf-8"}


def page(status=200, body=HTML, **headers) -> FetchedPage:
    base = dict(OK_HEADERS) if status == 200 else {}
    base.update({k.replace("_", "-"): v for k, v in headers.items()})
    return FetchedPage(status=status, headers=base, body=body if status == 200 else b"")


class Net:
    """Fake DNS and fake request. `web` maps (host, target) to the page to answer."""

    def __init__(self, web=None, dns=None):
        self.web = web or {}
        self.dns = dns or {}
        self.resolved: list[str] = []
        self.timeouts: list = []
        self.fetched: list[tuple[str, str, str]] = []  # (host, ip, target)

    def resolve(self, host, timeout=None):
        self.timeouts.append(timeout)
        self.resolved.append(host)
        answer = self.dns.get(host, [PUBLIC])
        if isinstance(answer, Exception):
            raise answer
        return list(answer)

    def fetch(self, host, ip, target, deadline, clock):
        self.fetched.append((host, ip, target))
        answer = self.web.get((host, target), page())
        if isinstance(answer, Exception):
            raise answer
        return answer

    def check(self, url, is_duplicate=lambda n: False, **kw):
        return check_link(url, resolver=self.resolve, fetcher=self.fetch, is_duplicate=is_duplicate, **kw)


def redirect(location, status=302) -> FetchedPage:
    return FetchedPage(status=status, headers={"location": location}, body=b"")


# --- 1. format ------------------------------------------------------------------------------

class TestFormat:
    @pytest.mark.parametrize(
        "url",
        [
            "http://docs.python.org/3/",
            "HTTP://docs.python.org/3/",
            "ftp://docs.python.org/",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "//docs.python.org/3/",
            "docs.python.org/3/",
            "https://",
            "",
            "   ",
            "https://user@docs.python.org/",
            "https://user:pw@docs.python.org/",
            "https://docs.python.org@evil.com/",
            "https://docs.python.org:8443/",
            "https://docs.python.org:80/",
            "https://docs.python.org:99999/",
            "https://docs.python.org:abc/",
            "https://docs.python.org/" + "a" * 2048,
            "https://docs.python.org/a b",
            "https://docs.python.org/a\tb",
            "https://docs.python.org/a\nb",
            "https://docs.python.org/a\\@evil.com",
            "https://docs.python.org/\x00",
        ],
    )
    def test_bad_format_is_refused_before_any_lookup(self, url):
        net = Net()
        result = net.check(url)
        assert (result.ok, result.code) == (False, BAD_URL)
        assert net.resolved == [] and net.fetched == []

    def test_a_non_string_is_refused(self):
        assert Net().check(None).code == BAD_URL  # type: ignore[arg-type]

    def test_exactly_2048_characters_is_fine_for_the_format(self):
        url = "https://docs.python.org/" + "a" * (2048 - len("https://docs.python.org/"))
        assert parse_url(url).host == "docs.python.org"

    def test_the_fragment_is_dropped(self):
        parsed = parse_url("https://docs.python.org/3/tutorial/#section")
        assert "#" not in parsed.normalized and "#" not in parsed.target

    def test_the_default_port_and_upper_case_are_fine(self):
        assert parse_url("HTTPS://DOCS.Python.ORG:443/3/").host == "docs.python.org"

    def test_whitespace_around_the_link_is_trimmed(self):
        assert parse_url("  https://docs.python.org/3/\n").host == "docs.python.org"


# --- 2. allowed domain ----------------------------------------------------------------------

class TestAllowedDomain:
    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.com/",
            "https://docs.python.org.evil.com/",
            "https://evil.com/docs.python.org",
            "https://evil.com/?next=docs.python.org",
            "https://evil.com#@docs.python.org/",
            "https://sub.docs.python.org/",
            "https://www.docs.python.org/",
            "https://python.org/",
            "https://org/",
            "https://docs.python.org./",  # a trailing dot is not an exact match
            "https://docs.python.org.:443/",
            "https://dеvelоper.mozilla.org/",  # Cyrillic е and о
            "https://docs.pythоn.org/",  # Cyrillic о
            "https://ｄｏｃｓ.python.org/",  # full-width letters
            "https://docs.python.org。evil.com/",  # ideographic full stop
            "https://xn--docs-python-9n9d.org/",  # punycode
            "https://xn--80ak6aa92e.com/",
            "https://localhost/",
            "https://127.0.0.1/",
            "https://2130706433/",  # decimal IPv4
            "https://0x7f000001/",  # hexadecimal IPv4
            "https://0177.0.0.1/",  # octal IPv4
            "https://169.254.169.254/latest/meta-data/",
            "https://0.0.0.0/",
            "https://[::1]/",
            "https://[fc00::1]/",
            "https://[fe80::1]/",
            "https://[::ffff:127.0.0.1]/",
        ],
    )
    def test_a_host_outside_the_list_is_refused_before_any_lookup(self, url):
        net = Net()
        result = net.check(url)
        assert (result.ok, result.code) == (False, NOT_ALLOWED_DOMAIN), url
        assert net.resolved == [] and net.fetched == []

    def test_every_listed_domain_is_accepted_and_nothing_else_is(self):
        for host in allowed_domains():
            assert parse_url(f"https://{host}/x").host == host
        assert len(allowed_domains()) == 34

    def test_a_pass_reports_the_source_name_of_the_domain(self):
        result = Net().check("https://docs.python.org/3/tutorial/")
        assert result.ok and result.domain == "docs.python.org" and result.source_name == allowed_domains()["docs.python.org"]


# --- 3. private addresses -------------------------------------------------------------------

class TestAddresses:
    @pytest.mark.parametrize(
        "address",
        [
            "127.0.0.1", "127.255.255.254", "10.0.0.1", "172.16.0.1", "172.31.255.255", "192.168.0.1", "169.254.169.254",
            "169.254.0.1", "0.0.0.0", "255.255.255.255", "224.0.0.1", "240.0.0.1", "100.64.0.1", "192.0.2.1", "198.18.0.1",
            "::1", "::", "fc00::", "fd12:3456::1", "fe80::1", "fe80::1%eth0", "ff02::1",
            "::ffff:127.0.0.1", "::ffff:10.0.0.1", "::ffff:169.254.169.254", "64:ff9b::7f00:1", "2002:7f00:1::", "2001:0:4136:e378:8000:63bf:3fff:fdd2",
            "2130706433", "0x7f000001", "localhost", "not-an-ip", "",
        ],
    )
    def test_an_allowed_host_that_resolves_to_a_non_public_address_is_refused(self, address):
        net = Net(dns={"docs.python.org": [address]})
        result = net.check("https://docs.python.org/3/")
        assert (result.ok, result.code) == (False, PRIVATE_ADDRESS), address
        assert net.fetched == []  # nothing was requested

    @pytest.mark.parametrize("mixed", [[PUBLIC, "10.0.0.1"], ["10.0.0.1", PUBLIC], [PUBLIC, "::1"], ["2606:4700::6810:85e5", "127.0.0.1"]])
    def test_one_private_address_among_public_ones_refuses_the_host(self, mixed):
        net = Net(dns={"docs.python.org": mixed})
        assert net.check("https://docs.python.org/3/").code == PRIVATE_ADDRESS
        assert net.fetched == []

    @pytest.mark.parametrize("address", [PUBLIC, "8.8.8.8", "2606:4700::6810:85e5", "151.101.1.69", "::ffff:93.184.216.34"])
    def test_public_addresses_pass(self, address):
        net = Net(dns={"docs.python.org": [address]})
        assert net.check("https://docs.python.org/3/").ok and net.fetched[0][1] == address

    def test_dns_failure_and_an_empty_answer_are_refused(self):
        assert Net(dns={"docs.python.org": socket.gaierror("no")}).check("https://docs.python.org/").code == DNS_FAILED
        assert Net(dns={"docs.python.org": OSError("x")}).check("https://docs.python.org/").code == DNS_FAILED
        assert Net(dns={"docs.python.org": []}).check("https://docs.python.org/").code == DNS_FAILED

    def test_a_dns_timeout_is_a_timeout(self):
        assert Net(dns={"docs.python.org": TimeoutError()}).check("https://docs.python.org/").code == TIMEOUT


# --- 4. DNS rebinding -----------------------------------------------------------------------

class TestDnsRebinding:
    def test_the_connection_goes_to_the_checked_address_and_dns_is_asked_once(self):
        answers = [[PUBLIC], ["127.0.0.1"], ["169.254.169.254"]]  # a second lookup would return a private address

        class Rebinder(Net):
            def resolve(self, host, timeout=None):
                self.resolved.append(host)
                return answers[len(self.resolved) - 1]

        net = Rebinder()
        result = net.check("https://docs.python.org/3/")
        assert result.ok
        assert net.resolved == ["docs.python.org"]  # one lookup for one hop
        assert [ip for _, ip, _ in net.fetched] == [PUBLIC]  # and only that address was used

    def test_every_hop_is_resolved_once_and_connected_with_its_own_answer(self):
        net = Net(
            web={("docs.python.org", "/a"): redirect("https://nextjs.org/b"), ("nextjs.org", "/b"): page()},
            dns={"docs.python.org": ["93.184.216.34"], "nextjs.org": ["151.101.1.69"]},
        )
        assert net.check("https://docs.python.org/a").ok
        assert net.resolved == ["docs.python.org", "nextjs.org"]
        assert net.fetched == [("docs.python.org", "93.184.216.34", "/a"), ("nextjs.org", "151.101.1.69", "/b")]

    def test_the_real_connection_uses_the_given_ip_and_keeps_the_host_name_for_tls(self, monkeypatch):
        calls = {}

        class FakeSock:
            def settimeout(self, value):
                calls["settimeout"] = value

        def create_connection(address, timeout=None, *a, **k):
            calls["address"], calls["timeout"] = address, timeout
            return FakeSock()

        class FakeContext:
            def wrap_socket(self, sock, server_hostname=None):
                calls["server_hostname"] = server_hostname
                return sock

        def no_dns(*a, **k):
            raise AssertionError("a second DNS lookup happened while connecting")

        monkeypatch.setattr(socket, "create_connection", create_connection)
        monkeypatch.setattr(socket, "getaddrinfo", no_dns)
        monkeypatch.setattr(socket, "gethostbyname", no_dns)
        conn = link_checker._PinnedHTTPSConnection("docs.python.org", PUBLIC, 3.0, FakeContext())
        conn.connect()
        assert calls["address"] == (PUBLIC, 443) and calls["timeout"] == 3.0
        assert calls["server_hostname"] == "docs.python.org"
        assert conn.host == "docs.python.org"  # the Host header and the certificate name

    def test_the_real_connection_verifies_the_certificate(self):
        context = link_checker._connect("docs.python.org", PUBLIC, 3.0)._context
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True


# --- 6. redirects ---------------------------------------------------------------------------

class TestRedirects:
    def test_a_redirect_inside_the_allowed_list_is_followed_and_reported(self):
        net = Net(web={("docs.python.org", "/a"): redirect("https://docs.python.org/b", 301), ("docs.python.org", "/b"): page()})
        result = net.check("https://docs.python.org/a")
        assert result.ok and result.url.endswith("/a") and result.final_url == "https://docs.python.org/b"

    def test_a_relative_location_is_resolved_against_the_current_address(self):
        net = Net(web={("docs.python.org", "/a/b"): redirect("../c"), ("docs.python.org", "/c"): page()})
        assert net.check("https://docs.python.org/a/b").final_url == "https://docs.python.org/c"

    @pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
    def test_each_redirect_status_is_handled_by_hand(self, status):
        net = Net(web={("docs.python.org", "/a"): redirect("/b", status), ("docs.python.org", "/b"): page()})
        assert net.check("https://docs.python.org/a").ok

    @pytest.mark.parametrize(
        "location",
        [
            "https://evil.com/",
            "//evil.com/x",
            "https://docs.python.org.evil.com/",
            "http://docs.python.org/b",  # back to plain http
            "ftp://docs.python.org/b",
            "https://127.0.0.1/",
            "https://169.254.169.254/latest/meta-data/",
            "https://2130706433/",
            "https://localhost/",
            "https://[::1]/",
            "https://user@docs.python.org/b",
            "https://docs.python.org:8443/b",
            "javascript:alert(1)",
        ],
    )
    def test_a_redirect_to_anything_refused_is_rejected_and_not_requested(self, location):
        net = Net(web={("docs.python.org", "/a"): redirect(location)})
        result = net.check("https://docs.python.org/a")
        assert (result.ok, result.code) == (False, BAD_REDIRECT), location
        assert net.fetched == [("docs.python.org", PUBLIC, "/a")] and net.resolved == ["docs.python.org"]

    def test_a_redirect_to_an_allowed_host_that_resolves_privately_is_refused_without_a_request(self):
        net = Net(web={("docs.python.org", "/a"): redirect("https://nextjs.org/b")}, dns={"nextjs.org": ["10.0.0.5"]})
        result = net.check("https://docs.python.org/a")
        assert result.code == PRIVATE_ADDRESS and len(net.fetched) == 1

    def test_three_redirects_are_fine_and_a_fourth_is_refused(self):
        web = {("docs.python.org", f"/{i}"): redirect(f"/{i + 1}") for i in range(0, 6)}
        web[("docs.python.org", "/3")] = page()
        assert Net(web=web).check("https://docs.python.org/0").ok  # /0 -> /1 -> /2 -> /3
        web[("docs.python.org", "/3")] = redirect("/4")
        web[("docs.python.org", "/4")] = page()
        net = Net(web=web)
        result = net.check("https://docs.python.org/0")  # four redirects
        assert (result.ok, result.code) == (False, BAD_REDIRECT) and len(net.fetched) == 4

    def test_a_loop_and_a_self_redirect_are_refused(self):
        assert Net(web={("docs.python.org", "/a"): redirect("/b"), ("docs.python.org", "/b"): redirect("/a")}).check("https://docs.python.org/a").code == BAD_REDIRECT
        assert Net(web={("docs.python.org", "/a"): redirect("/a")}).check("https://docs.python.org/a").code == BAD_REDIRECT
        assert Net(web={("docs.python.org", "/a"): redirect("/A/../a?utm_source=x")}).check("https://docs.python.org/a").code == BAD_REDIRECT

    def test_a_redirect_without_location_is_a_bad_status(self):
        assert Net(web={("docs.python.org", "/a"): FetchedPage(302, {}, b"")}).check("https://docs.python.org/a").code == BAD_STATUS

    def test_every_hop_repeats_the_whole_check(self):
        net = Net(web={("docs.python.org", "/a"): redirect("https://nextjs.org/b"), ("nextjs.org", "/b"): page(content_type="application/pdf")})
        assert net.check("https://docs.python.org/a").code == BAD_TYPE  # the response check runs on the last hop too
        assert net.resolved == ["docs.python.org", "nextjs.org"]

    def test_the_final_address_may_be_a_duplicate(self):
        net = Net(web={("docs.python.org", "/a"): redirect("/known"), ("docs.python.org", "/known"): page()})
        result = net.check("https://docs.python.org/a", is_duplicate=lambda n: n.endswith("/known"))
        assert result.code == DUPLICATE


# --- 5. time and size, the real request code ------------------------------------------------

class FakeResponse:
    def __init__(self, status=200, headers=None, chunks=None, clock=None, per_read=0.0, stream=False):
        self.status = status
        self._headers = headers if headers is not None else [("Content-Type", "text/html")]
        self._chunks = list(chunks or [])
        self._clock, self._per_read, self._stream = clock, per_read, stream
        self.consumed = 0
        self.read_sizes: list[int] = []

    def getheaders(self):
        return self._headers

    def read(self, amount=None):
        self.read_sizes.append(amount)
        if self._clock is not None:
            self._clock.now += self._per_read
        if self._stream:
            chunk = b"x" * amount
        elif self._chunks:
            chunk = self._chunks.pop(0)[:amount]
        else:
            chunk = b""
        self.consumed += len(chunk)
        return chunk


class FakeConnection:
    def __init__(self, response=None, clock=None, request_cost=0.0, response_cost=0.0, error=None, response_error=None):
        self.response, self.clock = response, clock
        self.request_cost, self.response_cost, self.error, self.response_error = request_cost, response_cost, error, response_error
        self.sock = None
        self.closed = False
        self.sent = None

    def request(self, method, target, headers=None):
        if self.clock:
            self.clock.now += self.request_cost
        if self.error:
            raise self.error
        self.sent = (method, target, headers)

    def getresponse(self):
        if self.clock:
            self.clock.now += self.response_cost
        if self.response_error:
            raise self.response_error
        return self.response

    def close(self):
        self.closed = True


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def run_fetch(connection, clock=None, deadline_in=8.0):
    clock = clock or Clock()
    seen = {}

    def connect(host, ip, timeout):
        seen.update(host=host, ip=ip, timeout=timeout)
        return connection

    return fetch_head("docs.python.org", PUBLIC, "/x", clock() + deadline_in, clock, connect), seen


class TestLimits:
    def test_the_request_is_a_plain_get_with_a_fixed_user_agent_and_no_cookie(self):
        conn = FakeConnection(FakeResponse(chunks=[b"<html>"]))
        run_fetch(conn)
        method, target, headers = conn.sent
        assert (method, target) == ("GET", "/x")
        assert headers["User-Agent"] == link_checker.USER_AGENT and "Cookie" not in headers and "Authorization" not in headers
        assert headers["Accept-Encoding"] == "identity" and conn.closed

    def test_the_connect_timeout_is_three_seconds_at_most(self):
        _, seen = run_fetch(FakeConnection(FakeResponse(chunks=[b"a"])))
        assert seen["timeout"] == 3.0 and seen["ip"] == PUBLIC and seen["host"] == "docs.python.org"
        _, seen = run_fetch(FakeConnection(FakeResponse(chunks=[b"a"])), deadline_in=1.5)
        assert seen["timeout"] == 1.5

    def test_only_the_first_128_kb_are_read_and_the_rest_is_never_requested(self):
        response = FakeResponse(stream=True)
        fetched, _ = run_fetch(FakeConnection(response))
        assert len(fetched.body) == 128 * 1024 and response.consumed == 128 * 1024
        assert sum(response.read_sizes) <= 128 * 1024 + 8192 and max(response.read_sizes) <= 8192

    def test_a_large_page_still_passes_with_the_metadata_of_its_head(self):
        head = b"<html><head><title>Big Page</title></head><body>"
        net = Net(web={("docs.python.org", "/big"): page(body=head + b"y" * (128 * 1024))})
        assert net.check("https://docs.python.org/big").metadata.title == "Big Page"

    def test_a_server_that_sends_one_byte_at_a_time_is_cut_off_at_the_total_time(self):
        clock = Clock()
        response = FakeResponse(stream=True, clock=clock, per_read=3.0)
        with pytest.raises(FetchError) as err:
            run_fetch(FakeConnection(response, clock), clock)
        assert err.value.code == TIMEOUT and len(response.read_sizes) <= 3  # 3 s per read: dead after three reads

    def test_slow_response_headers_use_up_the_total_time(self):
        clock = Clock()
        conn = FakeConnection(FakeResponse(chunks=[b"abc"]), clock, response_cost=9.0)
        with pytest.raises(FetchError) as err:
            run_fetch(conn, clock)
        assert err.value.code == TIMEOUT and conn.closed

    def test_a_deadline_that_has_already_passed_never_connects(self):
        called = []
        with pytest.raises(FetchError) as err:
            fetch_head("docs.python.org", PUBLIC, "/", 99.0, Clock(), lambda *a: called.append(a))
        assert err.value.code == TIMEOUT and called == []

    @pytest.mark.parametrize(
        "error, code",
        [
            (socket.timeout("slow"), TIMEOUT),
            (TimeoutError(), TIMEOUT),
            (ssl.SSLCertVerificationError("bad cert"), FETCH_FAILED),
            (ConnectionRefusedError(), FETCH_FAILED),
            (ConnectionResetError(), FETCH_FAILED),
            (http.client.BadStatusLine("x"), FETCH_FAILED),
            (http.client.IncompleteRead(b""), FETCH_FAILED),
            (http.client.LineTooLong("header line"), TOO_LARGE),
        ],
    )
    def test_request_errors_are_mapped_to_codes(self, error, code):
        for conn in (FakeConnection(error=error), FakeConnection(response_error=error)):
            with pytest.raises(FetchError) as err:
                run_fetch(conn)
            assert err.value.code == code and conn.closed

    def test_a_redirect_body_is_not_read(self):
        response = FakeResponse(status=302, headers=[("Location", "/b")], chunks=[b"never read"])
        fetched, _ = run_fetch(FakeConnection(response))
        assert fetched.status == 302 and fetched.headers["location"] == "/b" and fetched.body == b"" and response.read_sizes == []

    def test_header_names_are_lower_cased_and_the_first_value_wins(self):
        response = FakeResponse(headers=[("Content-Type", "text/html"), ("content-type", "application/pdf")], chunks=[b"a"])
        fetched, _ = run_fetch(FakeConnection(response))
        assert fetched.headers["content-type"] == "text/html"

    def test_check_link_maps_a_slow_or_failing_request_to_its_code(self):
        net = Net(web={("docs.python.org", "/slow"): FetchError(TIMEOUT), ("docs.python.org", "/big"): FetchError(TOO_LARGE)})
        assert net.check("https://docs.python.org/slow").code == TIMEOUT
        assert net.check("https://docs.python.org/big").code == TOO_LARGE

    def test_the_next_checked_address_is_tried_after_a_refused_connection_but_not_after_a_timeout(self):
        net = Net(dns={"docs.python.org": [PUBLIC, "151.101.1.69"]})
        calls = []

        def fetcher(host, ip, target, deadline, clock):
            calls.append(ip)
            if ip == PUBLIC:
                raise FetchError(FETCH_FAILED)
            return page()

        assert check_link("https://docs.python.org/", resolver=net.resolve, fetcher=fetcher, is_duplicate=lambda n: False).ok
        assert calls == [PUBLIC, "151.101.1.69"]
        calls.clear()

        def slow(host, ip, target, deadline, clock):
            calls.append(ip)
            raise FetchError(TIMEOUT)

        assert check_link("https://docs.python.org/", resolver=net.resolve, fetcher=slow, is_duplicate=lambda n: False).code == TIMEOUT
        assert calls == [PUBLIC]


class TestDnsTime:
    """The DNS wait is part of the same 8 seconds as the request (it used to be added per hop)."""

    class SlowDns(Net):
        def __init__(self, clock, cost, **kw):
            super().__init__(**kw)
            self.clock, self.cost = clock, cost

        def resolve(self, host, timeout=None):
            self.clock.now += self.cost
            return super().resolve(host, timeout)

    def hops(self):
        return {("docs.python.org", f"/{i}"): redirect(f"/{i + 1}") for i in range(3)} | {("docs.python.org", "/3"): page()}

    def test_the_resolver_is_told_how_long_it_may_take_and_the_total_is_kept(self):
        clock = Clock()
        net = self.SlowDns(clock, 2.5, web=self.hops())
        result = net.check("https://docs.python.org/0", clock=clock)
        assert (result.ok, result.code) == (False, TIMEOUT)
        assert net.timeouts == [3.0, 3.0, 3.0, 0.5]  # min(3 s, what is left of the 8 s)
        assert len(net.fetched) == 3  # the fourth hop never got a request

    def test_a_dns_answer_that_arrives_after_the_deadline_is_a_timeout(self):
        clock = Clock()
        net = self.SlowDns(clock, 9.0)
        result = net.check("https://docs.python.org/", clock=clock)
        assert result.code == TIMEOUT and net.fetched == []

    def test_a_fast_dns_leaves_the_budget_alone(self):
        clock = Clock()
        net = self.SlowDns(clock, 0.1, web=self.hops())
        assert net.check("https://docs.python.org/0", clock=clock).ok
        assert net.timeouts == [3.0] * 4

    def test_stuck_lookups_do_not_hang_the_next_one_and_the_pool_recovers(self, monkeypatch):
        import threading

        release = threading.Event()
        stuck = [link_checker._dns_pool.submit(release.wait, 30) for _ in range(4)]  # all four workers busy
        lookups = []
        monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: lookups.append(a) or [(2, 1, 6, "", (PUBLIC, 443))])
        try:
            started = time.monotonic()
            with pytest.raises(TimeoutError):
                link_checker.resolve_host("docs.python.org", timeout=0.2)
            assert time.monotonic() - started < 2.0  # it gave up; it did not wait for the stuck workers
            assert check_link("https://docs.python.org/", resolver=lambda h, t: link_checker.resolve_host(h, 0.2),
                              fetcher=Net().fetch, is_duplicate=lambda n: False).code == TIMEOUT
        finally:
            release.set()
            for future in stuck:
                future.result(timeout=5)
        assert lookups == []  # the two lookups that gave up were cancelled, they did not run later
        assert link_checker.resolve_host("docs.python.org", timeout=2.0) == [PUBLIC]  # free again
        assert len(lookups) == 1


# --- 7. response ----------------------------------------------------------------------------

class TestResponse:
    @pytest.mark.parametrize("status", [201, 204, 206, 400, 401, 403, 404, 410, 429, 500, 502, 503])
    def test_only_status_200_passes(self, status):
        net = Net(web={("docs.python.org", "/x"): FetchedPage(status, dict(OK_HEADERS), HTML)})
        assert net.check("https://docs.python.org/x").code == BAD_STATUS

    @pytest.mark.parametrize(
        "content_type",
        ["application/pdf", "application/json", "application/octet-stream", "text/plain", "image/png", "application/xhtml+xml", "", "html"],
    )
    def test_only_text_html_passes(self, content_type):
        headers = {"content-type": content_type} if content_type else {}
        net = Net(web={("docs.python.org", "/x"): FetchedPage(200, headers, HTML)})
        assert net.check("https://docs.python.org/x").code == BAD_TYPE

    @pytest.mark.parametrize("content_type", ["text/html", "TEXT/HTML", "text/html; charset=utf-8", " text/html ;charset=EUC-KR"])
    def test_text_html_in_any_spelling_passes(self, content_type):
        net = Net(web={("docs.python.org", "/x"): FetchedPage(200, {"content-type": content_type}, HTML)})
        assert net.check("https://docs.python.org/x").ok

    def test_a_compressed_body_is_refused_because_it_would_not_be_parsed(self):
        net = Net(web={("docs.python.org", "/x"): FetchedPage(200, {**OK_HEADERS, "content-encoding": "gzip"}, b"\x1f\x8b")})
        assert net.check("https://docs.python.org/x").code == BAD_TYPE

    @pytest.mark.parametrize("body", [b"", b"   \n\t "])
    def test_an_empty_body_is_refused(self, body):
        net = Net(web={("docs.python.org", "/x"): FetchedPage(200, dict(OK_HEADERS), body)})
        assert net.check("https://docs.python.org/x").code == EMPTY_BODY


# --- 8. duplicate ---------------------------------------------------------------------------

class TestDuplicate:
    def test_a_duplicate_is_refused_before_any_lookup(self):
        net = Net()
        result = net.check("https://docs.python.org/3/", is_duplicate=lambda n: True)
        assert (result.ok, result.code) == (False, DUPLICATE) and net.resolved == [] and net.fetched == []

    def test_a_catalog_link_is_a_duplicate_in_any_spelling(self):
        for url in [
            "https://docs.python.org/3/tutorial/",
            "https://docs.python.org/3/tutorial",
            "HTTPS://Docs.Python.org/3/tutorial/?utm_source=x&utm_medium=y#top",
            "https://docs.python.org/3/tutorial/?fbclid=abc",
        ]:
            net = Net()
            result = check_link(url, resolver=net.resolve, fetcher=net.fetch)  # the real duplicate check
            assert result.code == DUPLICATE, url
            assert net.resolved == []

    def test_a_pending_or_approved_candidate_is_a_duplicate_but_a_rejected_one_is_not(self):
        url = "https://docs.python.org/3/library/os.html"
        rejected = resource_store.create_candidate({"status": "rejected", "url": normalize_url(url)})
        net = Net()
        assert check_link(url, resolver=net.resolve, fetcher=net.fetch).ok
        resource_store.update_candidate(rejected["id"], {"status": "pending"})
        assert check_link(url, resolver=net.resolve, fetcher=net.fetch).code == DUPLICATE
        resource_store.update_candidate(rejected["id"], {"status": "approved"})
        assert check_link(url + "/?utm_source=a", resolver=net.resolve, fetcher=net.fetch).code == DUPLICATE

    def test_tracking_parameters_are_dropped_but_other_parameters_make_a_different_link(self):
        assert normalize_url("https://a.example/p/?utm_x=1&b=2&fbclid=z#f") == "https://a.example/p?b=2"
        assert normalize_url("https://a.example/p?id=1") != normalize_url("https://a.example/p?id=2")
        assert normalize_url("https://A.Example/P/") == "https://a.example/P"
        assert normalize_url("not a url") == "not a url"


# --- the result -----------------------------------------------------------------------------

class TestResult:
    def test_a_pass_lists_each_check(self):
        result = Net().check("https://docs.python.org/3/library/")
        assert result.ok and result.code is None
        assert result.checks == {"format": "pass", "domain": "pass", "duplicate": "pass", "address": "pass", "fetch": "pass", "response": "pass"}
        assert (result.metadata.title, result.metadata.description) == ("Python Tutorial", "Learn Python")

    def test_a_failure_names_the_stage_and_the_code(self):
        result = Net(dns={"docs.python.org": ["10.0.0.1"]}).check("https://docs.python.org/3/library/")
        assert result.checks["address"] == PRIVATE_ADDRESS and result.checks["domain"] == "pass"
        assert Net().check("http://docs.python.org/").checks == {"format": BAD_URL}

    def test_check_link_never_raises_on_odd_input(self):
        for url in ["\ud800", "https://" + "é" * 3000, "https://[", "https://docs.python.org:-1/", "\x00", "https://docs.python.org/%zz"]:
            Net().check(url)


# --- metadata reader ------------------------------------------------------------------------

class TestMetadata:
    def test_title_and_description(self):
        meta = extract_metadata(b"<html><head><title> My  Title </title><meta name='Description' content=' Short  text '></head></html>")
        assert (meta.title, meta.description) == ("My Title", "Short text")

    def test_no_title_gives_an_empty_string(self):
        assert extract_metadata(b"<html><head></head><body>hello</body></html>").title == ""
        assert extract_metadata(b"").title == ""

    def test_open_graph_values_fill_in_for_missing_ones(self):
        body = b'<head><meta property="og:title" content="OG Title"><meta property="og:description" content="OG Desc"></head>'
        meta = extract_metadata(body)
        assert (meta.title, meta.description) == ("OG Title", "OG Desc")

    def test_the_regular_values_win_over_open_graph(self):
        body = b'<head><title>Plain</title><meta property="og:title" content="OG"><meta name="description" content="Plain desc"><meta property="og:description" content="OG desc"></head>'
        meta = extract_metadata(body)
        assert (meta.title, meta.description) == ("Plain", "Plain desc")

    def test_long_values_are_cut(self):
        body = f"<title>{'가' * 500}</title><meta name='description' content='{'a' * 900}'>".encode()
        meta = extract_metadata(body)
        assert len(meta.title) == TITLE_MAX_CHARS and len(meta.description) == DESCRIPTION_MAX_CHARS

    def test_control_characters_are_removed(self):
        body = "<title>A\x00B\x07C‮D​E\x1b[31mF\r\nG</title>".encode()
        title = extract_metadata(body).title
        assert title == "ABCDE[31mF G" and not any(ord(c) < 32 for c in title)
        assert clean_text("a b c", 10) == "a b c"

    def test_markup_in_a_title_is_kept_as_plain_characters(self):
        assert extract_metadata(b"<title>&lt;script&gt;alert(1)&lt;/script&gt;</title>").title == "<script>alert(1)</script>"
        assert extract_metadata(b"<title><script>alert(1)</script></title>").title == "<script>alert(1)</script>"
        assert extract_metadata(b'<title><img src=x onerror=alert(1)></title>').title == "<img src=x onerror=alert(1)>"
        meta = extract_metadata(b'<meta name="description" content="&lt;b&gt;bold&lt;/b&gt; <i>x</i>">')
        assert meta.description == "<b>bold</b> <i>x</i>"

    def test_a_description_inside_a_script_or_the_body_is_ignored(self):
        body = b'<head><script>var m = \'<meta name="description" content="fake">\';</script></head><body><meta name="description" content="late"></body>'
        assert extract_metadata(body).description == ""

    def test_the_charset_comes_from_the_header_or_the_meta_tag(self):
        text = "<title>한국어 제목</title>"
        assert extract_metadata(text.encode("euc-kr"), "text/html; charset=euc-kr").title == "한국어 제목"
        assert extract_metadata(b'<meta charset="euc-kr">' + text.encode("euc-kr")).title == "한국어 제목"
        assert extract_metadata(text.encode("utf-8")).title == "한국어 제목"
        assert extract_metadata(text.encode("utf-8"), "text/html; charset=no-such-charset").title == "한국어 제목"

    def test_broken_html_never_raises(self):
        for body in [b"<title", b"<meta name=", b"<<<>>>", b"\xff\xfe\x00", b"<title>unclosed", b"<meta name='description'>"]:
            extract_metadata(body)
        assert extract_metadata(b"<title>unclosed text").title == "unclosed text"


# --- logging --------------------------------------------------------------------------------

class TestNothingIsLogged:
    SECRET = "secret-title-zebra-7731"

    def test_neither_the_address_nor_the_page_reach_the_log(self, caplog):
        body = f"<title>{self.SECRET}</title><meta name='description' content='{self.SECRET}-desc'>".encode()
        net = Net(web={("docs.python.org", "/zebra-path-9902"): page(body=body), ("docs.python.org", "/gone-zebra-9902"): FetchedPage(404, {}, b"")})
        with caplog.at_level(logging.DEBUG):
            assert net.check("https://docs.python.org/zebra-path-9902?token=abc123").ok
            assert net.check("https://docs.python.org/gone-zebra-9902").code == BAD_STATUS
            assert net.check("https://evil-host-4410.com/").code == NOT_ALLOWED_DOMAIN
        text = caplog.text
        for needle in (self.SECRET, "zebra-path-9902", "gone-zebra-9902", "evil-host-4410", "abc123", "docs.python.org"):
            assert needle not in text, needle
        assert "link check" in text  # the codes themselves are logged
