"""Safe storage of fetched PDFs under ``corpus/raw/`` (M1).

Path-traversal protection lives here: nothing a remote server or URL controls
is ever used as a path unless it first passes a strict whitelist.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

# Real SDS ids in corpus/raw/ are plain alphanumerics (e.g. 216763.pdf). The
# whitelist is deliberately narrower than "anything without a slash": no dots,
# so no "..", no hidden files, no extension tricks.
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


class UnsafePathError(ValueError):
    """Raised when a computed output path would escape the output directory."""


def safe_document_id(url: str) -> str:
    """Derive a filesystem-safe document id from a URL.

    Problem solved: a URL path segment is attacker-influenced (``../../x``,
    ``%2e%2e%2f``, absolute paths, Windows drive/backslash tricks). Why
    whitelist-or-hash: if the final path segment (after one percent-decode,
    extension stripped) is purely ``[A-Za-z0-9_-]``, it is used as-is, which
    keeps the existing ``<sds-id>.pdf`` naming (``216763.pdf``); anything else
    (or a URL whose path contains ``..`` or a backslash) is replaced by a
    truncated SHA-256 of the full URL, which is always safe
    and still stable/unique per URL. Sanitising by deleting bad characters
    was rejected because it can make two different URLs collide.

    Args:
        url: Absolute URL the document was fetched from.

    Returns:
        A string matching ``[A-Za-z0-9_-]{1,64}``.
    """
    decoded = unquote(urlsplit(url).path)
    fallback = "sds_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    if ".." in decoded.split("/") or "\\" in decoded:
        return fallback  # traversal-shaped URL: never derive a name from it
    segment = PurePosixPath(decoded).name
    stem = segment[:-4] if segment.lower().endswith(".pdf") else segment
    if _SAFE_ID_RE.fullmatch(stem):
        return stem
    return fallback


def resolve_output_path(output_dir: Path, document_id: str) -> Path:
    """Return ``<output_dir>/<document_id>.pdf``, guaranteed inside output_dir.

    Problem solved: defence in depth. Even if ``safe_document_id`` had a bug,
    or a caller passed its own id, a final check stops any write outside the
    raw corpus directory. Why resolve-then-compare: ``resolve()`` collapses
    ``..`` and follows symlinks, so the containment test judges where the
    write would *really* land, not how the string looks.

    Raises:
        UnsafePathError: if the id is not whitelisted or the resolved path
            escapes ``output_dir``.
    """
    if not _SAFE_ID_RE.fullmatch(document_id):
        raise UnsafePathError(f"unsafe document id: {document_id!r}")
    base = output_dir.resolve()
    target = (base / f"{document_id}.pdf").resolve()
    if not target.is_relative_to(base):
        raise UnsafePathError(f"path escapes output dir: {target}")
    return target


def save_pdf(output_dir: Path, url: str, content: bytes) -> Path:
    """Validate and write fetched bytes as a PDF; return the written path.

    Problem solved: ensures only real PDFs, at safe paths, land in the corpus
    that ``corpus/pdf_loader.py`` globs. Why check the ``%PDF-`` magic bytes:
    a server's Content-Type header can lie (or an HTML error page can arrive
    with a 200), and a non-PDF would crash pdfplumber later. Writing uses
    exclusive replace-on-temp so a partial download never looks like a PDF.
    """
    if not content.startswith(b"%PDF-"):
        raise ValueError("response body is not a PDF")
    target = resolve_output_path(output_dir, safe_document_id(url))
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    tmp.write_bytes(content)
    tmp.replace(target)
    return target
