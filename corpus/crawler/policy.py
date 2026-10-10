"""Crawl policy: domain allowlist, robots.txt compliance, politeness delay.

These three classes are the "good citizen + security" gate every request
passes through (Lecture 11; plan section on crawler security).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

_DEFAULT_PORTS = {"http": 80, "https": 443}


class DomainAllowlist:
    """Explicit list of hosts the crawler may contact.

    Problem solved: a link, redirect or malformed URL must never be able to
    steer the crawler to an arbitrary host (SSRF, fetching attacker-hosted
    content, hammering a site nobody approved). Why an allowlist and not a
    blocklist: the set of bad hosts is unbounded, the set of intended hosts
    is tiny and known. Entries are supplied at construction, never hardcoded.

    Matching rules: scheme must be http/https; an entry matches the same host
    or any true subdomain (``sigmaaldrich.com`` matches ``www.sigmaaldrich.com``
    but not ``evilsigmaaldrich.com``). Only default ports (80/443) are allowed
    unless the entry names a port explicitly (``127.0.0.1:8080``), which is
    what lets tests target a local server without loosening production use.
    """

    def __init__(self, domains: Iterable[str]) -> None:
        """Store the permitted hosts (lower-cased, optional ``host:port``)."""
        self._entries: list[tuple[str, int | None]] = []
        for raw in domains:
            host, _, port = raw.strip().lower().rstrip(".").partition(":")
            if host:
                self._entries.append((host, int(port) if port else None))

    def is_allowed(self, url: str) -> bool:
        """Return True only if ``url`` is http(s) and targets a permitted host.

        Problem solved: single choke point for the allowlist check. Why parse
        with ``urlsplit().hostname``: it ignores userinfo, so
        ``http://allowed.com@evil.com/`` is judged by ``evil.com``.
        """
        try:
            parts = urlsplit(url)
            host = (parts.hostname or "").lower().rstrip(".")
            port = parts.port
        except ValueError:
            return False
        if parts.scheme not in _DEFAULT_PORTS or not host:
            return False
        for entry_host, entry_port in self._entries:
            if host != entry_host and not host.endswith("." + entry_host):
                continue
            if entry_port is None:
                if port is None or port == _DEFAULT_PORTS[parts.scheme]:
                    return True
            elif port == entry_port:
                return True
        return False


class RobotsCache:
    """Fetches, caches and queries each host's robots.txt.

    Problem solved: robots.txt is the site owner's statement of what crawlers
    may fetch; ignoring it is both impolite and a legal/ethical risk. Why
    stdlib ``RobotFileParser`` with our own fetch: the parser handles the
    format correctly (no new dependency), but its built-in ``read()`` has no
    timeout and bypasses our allowlist/session, so we download the text
    ourselves and feed it to ``parse()``.

    Failure policy (RFC 9309): 404/other 4xx -> no rules, everything allowed;
    5xx, network error or non-HTTP failure -> assume everything disallowed
    until robots.txt can be read (fail closed).
    """

    def __init__(
        self,
        fetch: Callable[[str], requests.Response],
        user_agent: str,
    ) -> None:
        """Remember how to download robots.txt and which agent name to match."""
        self._fetch = fetch
        self._user_agent = user_agent
        self._parsers: dict[str, RobotFileParser] = {}

    def _parser_for(self, url: str) -> RobotFileParser:
        """Return (fetching on first use) the parser for ``url``'s origin."""
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._parsers:
            parser = RobotFileParser()
            try:
                response = self._fetch(origin + "/robots.txt")
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                elif 400 <= response.status_code < 500:
                    parser.parse([])  # no robots.txt -> allow all
                else:
                    parser.disallow_all = True
            except requests.RequestException:
                parser.disallow_all = True
            self._parsers[origin] = parser
        return self._parsers[origin]

    def can_fetch(self, url: str) -> bool:
        """Return True if robots.txt permits our agent to fetch ``url``."""
        return self._parser_for(url).can_fetch(self._user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        """Return the site's declared Crawl-delay for our agent, if any."""
        delay = self._parser_for(url).crawl_delay(self._user_agent)
        return float(delay) if delay is not None else None


class PolitenessLimiter:
    """Enforces a minimum gap between requests to the same host.

    Problem solved: a tight fetch loop looks like a denial-of-service attack
    to the server. Why per-host timestamps: politeness is owed to each
    server separately, so a slow crawl of one host should not delay another.
    The clock and sleep are injectable so tests run instantly and exactly.
    """

    def __init__(
        self,
        default_delay: float = 3.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Set the default gap (seconds); conservative 3s by default."""
        if default_delay < 0:
            raise ValueError("default_delay must be >= 0")
        self._default_delay = default_delay
        self._clock = clock
        self._sleep = sleep
        self._last_request: dict[str, float] = {}

    def wait(self, host: str, crawl_delay: float | None = None) -> float:
        """Block until a request to ``host`` is polite; return seconds slept.

        Problem solved: spaces requests out. Why ``max`` of our default and
        the site's Crawl-delay: we never go faster than the site asks, and
        never faster than our own floor.
        """
        delay = max(self._default_delay, crawl_delay or 0.0)
        slept = 0.0
        last = self._last_request.get(host)
        if last is not None:
            remaining = delay - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
                slept = remaining
        self._last_request[host] = self._clock()
        return slept
