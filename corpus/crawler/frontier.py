"""URL frontier for the SDS crawler (M1, Lecture 11).

The frontier is the crawler's to-do list: URLs discovered but not yet fetched.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalise_url(url: str) -> str:
    """Canonicalise a URL so trivially different spellings compare equal.

    Problem solved: without this, ``HTTP://Example.com:80/a#top`` and
    ``http://example.com/a`` would both be fetched, wasting requests against
    a server we are supposed to be polite to. Why this technique: a small
    deterministic rewrite (lower-case scheme/host, drop default port and
    fragment, empty path -> "/") is cheap and predictable, unlike fuzzy
    near-duplicate detection (Jaccard), which L11 reserves for page *content*.

    Args:
        url: Absolute URL (any case, may carry a fragment or default port).

    Returns:
        The canonical string form of the URL.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower().rstrip(".")
    port = parts.port
    netloc = host
    if port is not None and port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{host}:{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


@dataclass(frozen=True)
class FrontierEntry:
    """One queued URL plus how many hops from a seed it was discovered."""

    url: str
    depth: int = 0


class Frontier:
    """FIFO queue of URLs that remembers everything it has ever accepted.

    Problem solved: a crawler that follows links will meet the same URL again
    and again (navigation bars, cycles). Why a FIFO queue plus a seen-set:
    FIFO gives breadth-first order (shallow pages first, which keeps a small
    crawl focused near its seeds), and a hash set makes the "have we been
    here?" check O(1). A URL is marked seen when *enqueued*, not when fetched,
    so it cannot be queued twice while it is still waiting.
    """

    def __init__(self) -> None:
        """Create an empty frontier."""
        self._queue: deque[FrontierEntry] = deque()
        self._seen: set[str] = set()

    def add(self, url: str, depth: int = 0) -> bool:
        """Queue a URL unless it has been seen before.

        Problem solved: prevents revisiting. Why normalise first: so spelling
        variants of one URL count as the same page.

        Args:
            url: Absolute URL to enqueue.
            depth: Link distance from the seed that led here.

        Returns:
            True if the URL was newly queued, False if it was a duplicate.
        """
        canonical = normalise_url(url)
        if canonical in self._seen:
            return False
        self._seen.add(canonical)
        self._queue.append(FrontierEntry(canonical, depth))
        return True

    def pop(self) -> FrontierEntry | None:
        """Remove and return the next URL to fetch, or None when empty.

        Problem solved: hands the crawl loop work in discovery order. Why
        ``None`` rather than an exception: an empty frontier is the normal
        termination condition of a crawl, not an error.
        """
        return self._queue.popleft() if self._queue else None

    def __contains__(self, url: str) -> bool:
        """Report whether a URL has ever been accepted (queued or fetched)."""
        return normalise_url(url) in self._seen

    def __len__(self) -> int:
        """Number of URLs still waiting to be fetched."""
        return len(self._queue)
