"""SDS crawler: ties the frontier and the crawl policy together (M1, L11)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from corpus.crawler.frontier import Frontier
from corpus.crawler.policy import DomainAllowlist, PolitenessLimiter, RobotsCache
from corpus.crawler.storage import UnsafePathError, save_pdf

DEFAULT_USER_AGENT = "ChemSentryBot/0.1 (university coursework crawler; low rate)"
_MAX_REDIRECTS = 5
_MAX_BYTES = 50 * 1024 * 1024  # SDS PDFs are small; refuse anything huge
# Same folder corpus/pdf_loader.py reads, so crawled PDFs need no extra step.
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "raw"


@dataclass
class CrawlReport:
    """What a crawl did, so a run can be audited and asserted on in tests."""

    saved: list[Path] = field(default_factory=list)
    pages_fetched: int = 0
    blocked_by_allowlist: list[str] = field(default_factory=list)
    blocked_by_robots: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


class SDSCrawler:
    """Polite, allowlisted, breadth-first crawler that saves SDS PDFs.

    Problem solved: acquiring SDS documents from the web without being a bad
    citizen (robots.txt, delay) or a vulnerability (SSRF via redirects,
    arbitrary file writes). Why one orchestrating class over a script: the
    same gate (allowlist -> robots -> politeness -> bounded fetch) must wrap
    *every* request, including robots.txt itself and every redirect hop, and
    a single ``_request`` method makes that impossible to bypass by accident.
    """

    def __init__(
        self,
        allowed_domains: Iterable[str],
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        *,
        delay: float = 3.0,
        user_agent: str = DEFAULT_USER_AGENT,
        max_pages: int = 20,
        max_depth: int = 2,
        session: requests.Session | None = None,
        limiter: PolitenessLimiter | None = None,
        timeout: float = 15.0,
    ) -> None:
        """Configure a crawl.

        Args:
            allowed_domains: Hosts the crawler may contact (required, explicit).
            output_dir: Directory PDFs are written to (default ``corpus/raw``).
            delay: Minimum seconds between requests to one host (default 3).
            user_agent: Identifies us to site owners and robots.txt rules.
            max_pages: Hard cap on pages fetched -- this is a skeleton.
            max_depth: Link hops from a seed to follow.
            session: Injectable ``requests.Session`` (tests, proxies).
            limiter: Injectable limiter (tests pass a fake clock).
            timeout: Per-request timeout in seconds.
        """
        self.allowlist = DomainAllowlist(allowed_domains)
        self.output_dir = Path(output_dir)
        self.user_agent = user_agent
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.timeout = timeout
        self.frontier = Frontier()
        self._session = session or requests.Session()
        self._session.headers["User-Agent"] = user_agent
        self._limiter = limiter or PolitenessLimiter(delay)
        self._robots = RobotsCache(self._fetch_robots, user_agent)

    def _request(self, url: str, *, check_robots: bool) -> requests.Response:
        """Perform one gated GET, following redirects manually.

        Problem solved: ``requests`` follows redirects silently, so an allowed
        host could bounce us to a disallowed one. Why manual hops: each hop is
        re-checked against allowlist (and robots.txt for content pages) and
        re-throttled, so no redirect can skip a policy check.

        Raises:
            PermissionError: URL or a redirect hop violates the allowlist or
                robots.txt.
            requests.RequestException: network failure / too many redirects.
        """
        for _ in range(_MAX_REDIRECTS + 1):
            if not self.allowlist.is_allowed(url):
                raise PermissionError(f"domain not allowlisted: {url}")
            if check_robots and not self._robots.can_fetch(url):
                raise PermissionError(f"disallowed by robots.txt: {url}")
            # robots.txt itself has no robots rules to consult (and asking
            # would recurse), so only content pages pick up a Crawl-delay.
            crawl_delay = self._robots.crawl_delay(url) if check_robots else None
            self._limiter.wait(urlsplit(url).netloc.lower(), crawl_delay)
            response = self._session.get(
                url, allow_redirects=False, stream=True, timeout=self.timeout
            )
            if response.is_redirect and response.headers.get("Location"):
                url = urljoin(url, response.headers["Location"])
                response.close()
                continue
            return response
        raise requests.TooManyRedirects(f"more than {_MAX_REDIRECTS} redirects")

    def _fetch_robots(self, robots_url: str) -> requests.Response:
        """Download a robots.txt through the same allowlist/politeness gate.

        Problem solved: ``RobotsCache`` needs a fetcher that cannot itself
        reach a disallowed host. Why ``check_robots=False``: robots.txt is
        always fetchable; asking permission to read the permission file would
        be circular. The body is read eagerly (size-capped) for the parser.
        """
        response = self._request(robots_url, check_robots=False)
        response._content = response.raw.read(_MAX_BYTES, decode_content=True)
        response._content_consumed = True
        return response

    @staticmethod
    def _read_body(response: requests.Response) -> bytes:
        """Read a response body but refuse anything over the size cap.

        Problem solved: a hostile or broken server streaming gigabytes. Why
        read ``cap + 1``: lets us detect "too big" without buffering it all.
        """
        body = response.raw.read(_MAX_BYTES + 1, decode_content=True)
        if len(body) > _MAX_BYTES:
            raise ValueError("response larger than size cap")
        return body

    def _extract_links(self, page_url: str, html: bytes) -> list[str]:
        """Return absolute http(s) links found on an HTML page.

        Problem solved: discovering new documents from index/listing pages.
        Why BeautifulSoup rather than regex: HTML is not regular; real pages
        have odd quoting and nesting that break ad-hoc patterns.
        """
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for anchor in soup.find_all("a", href=True):
            absolute = urljoin(page_url, anchor["href"])
            if absolute.startswith(("http://", "https://")):
                links.append(absolute)
        return links

    def crawl(self, seed_urls: Iterable[str]) -> CrawlReport:
        """Crawl breadth-first from the seeds and save any PDFs found.

        Problem solved: the L11 crawl loop -- pop from the frontier, fetch,
        extract links, push new ones -- with every safety gate applied. Why
        ``max_pages``/``max_depth`` caps: a skeleton must be provably bounded;
        it should never wander a whole site.

        Args:
            seed_urls: Starting URLs (each must pass the allowlist).

        Returns:
            A CrawlReport describing saved files, blocks and errors.
        """
        report = CrawlReport()
        for seed in seed_urls:
            if self.allowlist.is_allowed(seed):
                self.frontier.add(seed, depth=0)
            else:
                report.blocked_by_allowlist.append(seed)

        while report.pages_fetched < self.max_pages:
            entry = self.frontier.pop()
            if entry is None:
                break
            try:
                response = self._request(entry.url, check_robots=True)
            except PermissionError as exc:
                bucket = (
                    report.blocked_by_robots
                    if "robots" in str(exc)
                    else report.blocked_by_allowlist
                )
                bucket.append(entry.url)
                continue
            except requests.RequestException as exc:
                report.errors[entry.url] = str(exc)
                continue

            report.pages_fetched += 1
            try:
                self._handle_response(entry.url, entry.depth, response, report)
            except (ValueError, UnsafePathError, OSError) as exc:
                report.errors[entry.url] = str(exc)
            finally:
                response.close()
        return report

    def _handle_response(
        self,
        url: str,
        depth: int,
        response: requests.Response,
        report: CrawlReport,
    ) -> None:
        """Save a PDF response or harvest links from an HTML one.

        Problem solved: decides what a fetched page *is*. Why content-type
        first, body second: we skip downloading bodies we do not want, but the
        PDF itself is still verified by magic bytes in ``save_pdf``.
        """
        if response.status_code != 200:
            report.errors[url] = f"HTTP {response.status_code}"
            return
        ctype = response.headers.get("Content-Type", "").lower()
        if "application/pdf" in ctype:
            report.saved.append(
                save_pdf(self.output_dir, url, self._read_body(response))
            )
        elif "text/html" in ctype and depth < self.max_depth:
            for link in self._extract_links(url, self._read_body(response)):
                if self.allowlist.is_allowed(link):
                    self.frontier.add(link, depth + 1)
