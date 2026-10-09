"""Crawler: frontier, robots.txt handling, politeness delay (M1, Lecture 11).

Security (plan, security section): every request passes the domain allowlist,
and every file write passes path-traversal protection (see ``storage``).
"""

from corpus.crawler.crawler import CrawlReport, SDSCrawler
from corpus.crawler.frontier import Frontier, normalise_url
from corpus.crawler.policy import DomainAllowlist, PolitenessLimiter, RobotsCache
from corpus.crawler.storage import (
    UnsafePathError,
    resolve_output_path,
    safe_document_id,
    save_pdf,
)

__all__ = [
    "CrawlReport",
    "DomainAllowlist",
    "Frontier",
    "PolitenessLimiter",
    "RobotsCache",
    "SDSCrawler",
    "UnsafePathError",
    "normalise_url",
    "resolve_output_path",
    "safe_document_id",
    "save_pdf",
]
