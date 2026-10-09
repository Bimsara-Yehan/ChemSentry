"""Offline tests for the SDS crawler (M1, Lecture 11).

No test touches the real internet: a throwaway ``http.server`` on 127.0.0.1
serves small fixture pages, robots.txt and fake PDFs, matching how the rest of
this suite avoids external services. Time is faked so the politeness delay is
asserted exactly and runs instantly.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from corpus.crawler import (
    DomainAllowlist,
    Frontier,
    PolitenessLimiter,
    SDSCrawler,
    UnsafePathError,
    normalise_url,
    resolve_output_path,
    safe_document_id,
    save_pdf,
)

FAKE_PDF = b"%PDF-1.4\n%fixture\n"
ROBOTS = "User-agent: *\nDisallow: /private/\nCrawl-delay: 1\n"
INDEX = (
    '<a href="/sds/216763.pdf">a</a> <a href="/private/secret.pdf">b</a>'
    '<a href="http://evil.example/x.pdf">c</a> <a href="/sds/216763.pdf#frag">d</a>'
    '<a href="/redir">e</a> <a href="/sds/..%2f..%2fevil.pdf">f</a>'
    '<a href="/fake.pdf">g</a>'
)


class _Handler(BaseHTTPRequestHandler):
    """Fixture site; records every path requested in ``server.hits``."""

    def log_message(self, *args: object) -> None:  # silence test output
        """Silence the default per-request stderr logging during tests."""
        pass

    def _send(self, status: int, ctype: str, body: bytes, extra=None) -> None:
        """Write one HTTP response with the given status, type and body."""
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        """Route fixture paths: robots.txt, index, redirect, fake and real PDFs."""
        self.server.hits.append(self.path)  # type: ignore[attr-defined]
        port = self.server.server_address[1]
        if self.path == "/robots.txt":
            self._send(200, "text/plain", ROBOTS.encode())
        elif self.path == "/":
            self._send(200, "text/html", INDEX.encode())
        elif self.path == "/redir":  # hop to a host that is NOT allowlisted
            self._send(
                302,
                "text/plain",
                b"",
                {"Location": f"http://localhost:{port}/sds/1.pdf"},
            )
        elif self.path == "/fake.pdf":  # claims PDF, is HTML
            self._send(200, "application/pdf", b"<html>not a pdf</html>")
        elif self.path.endswith(".pdf"):
            self._send(200, "application/pdf", FAKE_PDF)
        else:
            self._send(404, "text/plain", b"nope")


@pytest.fixture()
def site():
    """Start the fixture server; yield (base_url, host_entry, hits list)."""
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    server.hits = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield f"http://127.0.0.1:{port}", f"127.0.0.1:{port}", server.hits
    server.shutdown()


class FakeTime:
    """Deterministic clock whose sleep() just advances time."""

    def __init__(self) -> None:
        """Start the fake clock at an arbitrary fixed time."""
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        """Return the current fake time."""
        return self.now

    def sleep(self, seconds: float) -> None:
        """Record the requested sleep and advance fake time instantly."""
        self.sleeps.append(seconds)
        self.now += seconds


def _crawler(site, tmp_path: Path, ft: FakeTime, **kw) -> SDSCrawler:
    """Build a crawler allowlisted to the fixture site with a fake-clock limiter."""
    _, entry, _ = site
    return SDSCrawler(
        [entry],
        tmp_path,
        limiter=PolitenessLimiter(2.0, ft.clock, ft.sleep),
        **kw,
    )


# --- Frontier -------------------------------------------------------------


def test_frontier_never_revisits_and_is_fifo() -> None:
    """Frontier dedupes spelling variants, keeps fetched URLs seen, pops FIFO."""
    f = Frontier()
    assert f.add("http://a.com/x")
    assert not f.add("HTTP://A.com:80/x#frag")  # same page, different spelling
    assert f.add("http://a.com/y")
    assert "http://a.com/x" in f
    assert f.pop().url == "http://a.com/x"
    assert not f.add("http://a.com/x")  # fetched URLs stay "seen"
    assert f.pop().url == "http://a.com/y"
    assert f.pop() is None and len(f) == 0


def test_normalise_url_keeps_non_default_port_and_query() -> None:
    """Normalisation drops only what is redundant (default port, fragment)."""
    assert normalise_url("http://H.com:8080") == "http://h.com:8080/"
    assert normalise_url("https://h.com:443/a?q=1#z") == "https://h.com/a?q=1"


# --- Allowlist --------------------------------------------------------------


@pytest.mark.parametrize(
    "url,ok",
    [
        ("https://www.sigmaaldrich.com/doc.pdf", True),
        ("https://sigmaaldrich.com/doc.pdf", True),
        ("http://sigmaaldrich.com/x", True),
        ("https://evilsigmaaldrich.com/x", False),  # suffix trick
        ("https://sigmaaldrich.com.evil.io/x", False),
        ("https://sigmaaldrich.com@evil.io/x", False),  # userinfo trick
        ("https://sigmaaldrich.com:8443/x", False),  # non-default port
        ("ftp://sigmaaldrich.com/x", False),
        ("file:///etc/passwd", False),
        ("https:///nohost", False),
        ("not a url", False),
    ],
)
def test_allowlist_decisions(url: str, ok: bool) -> None:
    """Allowlist accepts the domain and true subdomains, rejects lookalikes."""
    assert DomainAllowlist(["sigmaaldrich.com"]).is_allowed(url) is ok


def test_allowlist_empty_allows_nothing() -> None:
    """An empty allowlist is deny-all, never allow-all."""
    assert not DomainAllowlist([]).is_allowed("https://anything.com/")


def test_crawler_refuses_seed_outside_allowlist(site, tmp_path: Path) -> None:
    """A non-allowlisted seed is reported and never requested."""
    c = _crawler(site, tmp_path, FakeTime())
    report = c.crawl(["http://evil.example/sds.pdf"])
    assert report.blocked_by_allowlist == ["http://evil.example/sds.pdf"]
    assert report.pages_fetched == 0 and not list(tmp_path.iterdir())


# --- Path traversal -----------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://h/sds/..%2f..%2fevil.pdf",
        "http://h/../../etc/passwd",
        "http://h/%2e%2e/%2e%2e/x.pdf",
        "http://h/a/..\\..\\win.pdf",
        "http://h/.hidden.pdf",
        "http://h/" + "a" * 200 + ".pdf",
        "http://h/",
    ],
)
def test_safe_document_id_never_contains_path_syntax(url: str) -> None:
    """Traversal-shaped URLs fall back to a hash id with only safe chars."""
    doc_id = safe_document_id(url)
    assert doc_id.startswith("sds_")  # fell back to the hash
    assert all(ch.isalnum() or ch in "_-" for ch in doc_id)


def test_safe_document_id_keeps_existing_naming_convention() -> None:
    """Real SDS ids keep the corpus/raw/<id>.pdf convention pdf_loader expects."""
    assert safe_document_id("https://x.com/sds/216763.pdf") == "216763"
    assert safe_document_id("https://x.com/sds/216763.pdf?v=1") == "216763"


def test_hash_fallback_is_stable_and_distinct() -> None:
    """Hash ids are deterministic per URL and differ between URLs."""
    a, b = "http://h/..%2fa.pdf", "http://h/..%2fb.pdf"
    assert safe_document_id(a) == safe_document_id(a) != safe_document_id(b)


def test_resolve_output_path_rejects_escape_and_bad_ids(tmp_path: Path) -> None:
    """Non-whitelisted ids are refused before any path is built."""
    for bad in ["../evil", "a/b", "..", "", "a.b", "x\\y"]:
        with pytest.raises(UnsafePathError):
            resolve_output_path(tmp_path, bad)
    assert resolve_output_path(tmp_path, "216763").parent == tmp_path.resolve()


def test_resolve_output_path_rejects_symlink_escape(tmp_path: Path) -> None:
    """A symlink planted in the output dir cannot redirect the write outside it."""
    outside = tmp_path / "outside"
    outside.mkdir()
    raw = tmp_path / "raw"
    raw.mkdir()
    try:
        (raw / "link.pdf").symlink_to(outside / "target.pdf")
    except (OSError, NotImplementedError):
        # Windows needs admin/Developer Mode to create symlinks.
        pytest.skip("symlinks not permitted on this machine")
    with pytest.raises(UnsafePathError):
        resolve_output_path(raw, "link")


def test_save_pdf_rejects_non_pdf_and_writes_inside_dir(tmp_path: Path) -> None:
    """Only %PDF bodies are written, always inside the output dir, no temp left."""
    with pytest.raises(ValueError):
        save_pdf(tmp_path, "http://h/1.pdf", b"<html></html>")
    path = save_pdf(tmp_path, "http://h/..%2f..%2fevil.pdf", FAKE_PDF)
    assert path.parent == tmp_path.resolve() and path.read_bytes() == FAKE_PDF
    assert not list(tmp_path.glob("*.part"))


# --- Politeness delay -------------------------------------------------------


def test_politeness_waits_between_same_host_requests() -> None:
    """Second request to a host waits the delay; other hosts are independent."""
    ft = FakeTime()
    lim = PolitenessLimiter(3.0, ft.clock, ft.sleep)
    assert lim.wait("a.com") == 0  # first request is free
    assert lim.wait("a.com") == 3.0
    assert lim.wait("b.com") == 0  # other host unaffected
    ft.now += 10
    assert lim.wait("a.com") == 0  # already waited long enough


def test_politeness_honours_larger_crawl_delay() -> None:
    """A robots.txt Crawl-delay above our default wins."""
    ft = FakeTime()
    lim = PolitenessLimiter(1.0, ft.clock, ft.sleep)
    lim.wait("a.com", crawl_delay=5)
    assert lim.wait("a.com", crawl_delay=5) == 5.0


def test_negative_delay_rejected() -> None:
    """A negative delay is a configuration error, not 'no delay'."""
    with pytest.raises(ValueError):
        PolitenessLimiter(-1)


# --- End-to-end against the local fixture site --------------------------------


def test_crawl_respects_robots_allowlist_and_saves_pdf(site, tmp_path: Path) -> None:
    """End-to-end: robots first, disallow honoured, no revisit, safe save, polite."""
    base, _, hits = site
    ft = FakeTime()
    report = _crawler(site, tmp_path, ft).crawl([base + "/"])

    # robots.txt fetched before the first content page
    assert hits[0] == "/robots.txt"
    # Disallowed path never requested; off-allowlist host never contacted
    assert "/private/secret.pdf" not in hits
    assert report.blocked_by_robots == [base + "/private/secret.pdf"]
    # The real PDF was saved under the existing <id>.pdf convention, once
    assert [p.name for p in report.saved].count("216763.pdf") == 1
    assert hits.count("/sds/216763.pdf") == 1  # fragment variant not revisited
    # Redirect to a non-allowlisted host (localhost vs 127.0.0.1) was refused
    assert "/sds/1.pdf" not in hits
    assert report.blocked_by_allowlist  # the redirect hop was recorded as blocked
    # Traversal-looking link stayed inside the output dir
    assert all(p.parent == tmp_path.resolve() for p in report.saved)
    assert not (tmp_path.parent / "evil.pdf").exists()
    # A fake "PDF" (HTML body) was rejected, not saved
    assert any("not a PDF" in msg for msg in report.errors.values())
    # Politeness: every gap to the host honoured max(2.0, Crawl-delay 1)
    assert ft.sleeps and all(s == pytest.approx(2.0) for s in ft.sleeps)


def test_crawl_is_bounded_by_max_pages(site, tmp_path: Path) -> None:
    """The skeleton never fetches more than max_pages."""
    base, _, _ = site
    report = _crawler(site, tmp_path, FakeTime(), max_pages=1).crawl([base + "/"])
    assert report.pages_fetched == 1


def test_robots_unreachable_fails_closed(tmp_path: Path) -> None:
    """With nothing listening, robots.txt cannot be read -> nothing is fetched."""
    c = SDSCrawler(
        ["127.0.0.1:9"],
        tmp_path,
        limiter=PolitenessLimiter(0, lambda: 0.0, lambda s: None),
        timeout=1,
    )
    report = c.crawl(["http://127.0.0.1:9/a.pdf"])
    assert report.saved == [] and report.blocked_by_robots
