"""Local PDF loader for real Safety Data Sheets (M1).

This is deliberately NOT the crawler (`corpus/crawler/`). The crawler's job is
acquiring documents from the web (frontier scheduling, robots.txt, politeness
delays). This module handles a different acquisition path: SDS PDFs a team
member already has on disk (`corpus/raw/`), which just need their text pulled
out before they can enter the same extraction pipeline as anything the
crawler eventually fetches.

Why pdfplumber and not PyPDF2/pymupdf:
    pdfplumber preserves reading order and spacing well enough for the regex
    extractors in `extraction/value_extractor.py` to work against, and it has
    no external binary dependency (unlike pdf2image/poppler). Real SDS PDFs
    are text-based (selectable text), not scanned images, so OCR is not
    needed for this corpus.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pdfplumber

from extraction.models import SDSMetadata
from extraction.section_splitter import split_sections

# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def extract_text_from_pdf(path: Path) -> str:
    """Extract raw text from a local PDF file, page by page, in order.

    Args:
        path: Path to a local SDS PDF.

    Returns:
        Full document text with page breaks joined by newlines.
    """
    with pdfplumber.open(path) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages)


# ---------------------------------------------------------------------------
# Minimal Section-1 metadata parsing
# ---------------------------------------------------------------------------

# Real SDS Section 1 text is field-labelled, not prose -- a much simpler
# pattern than the Section 7+ value extraction problem. Labels differ by
# supplier, each form below confirmed against a real SDS PDF:
#   Sigma-Aldrich:  "Product name : Tetrahydrofuran"
#   PanReac/ITW:    "Trade name:2-Propanol"
#   Carl Roth:      "Identification of the substance Ethanol" (no colon)
# The Carl Roth form must not match the Section 1 heading itself
# ("Identification of the substance/mixture and of the company/undertaking"),
# hence the (?!/) guard.
_PRODUCT_NAME_PATTERNS = (
    re.compile(r"Product\s*name\s*:?\s*(\S.*)", re.IGNORECASE),
    re.compile(r"Trade\s*name[ \t]*:[ \t]*(\S.*)", re.IGNORECASE),
    re.compile(
        r"Identification\s+of\s+the\s+substance(?!/)[ \t]*:?[ \t]+(\S.*)", re.IGNORECASE
    ),
)
# "CAS-No. : 109-99-9" (Sigma), "CAS number 64-17-5" (Carl Roth), and
# "CAS Number:\n7722-64-7" (PanReac -- value on the next line).
_CAS_NUMBER_RE = re.compile(
    r"CAS[-\s]?(?:No\.?|number)\s*:?\s*(\d{2,7}-\d{2}-\d)", re.IGNORECASE
)
# Colon required: without it, "Company" also matched the Section 1 heading
# "...of the company/undertaking" and recorded the supplier as "/undertaking".
_SUPPLIER_LABEL_PATTERNS = (
    re.compile(r"Company[ \t]*:[ \t]*(\S.*)", re.IGNORECASE),
    re.compile(r"Manufacturer\s*/\s*Supplier\s*:\s*(\S.*)", re.IGNORECASE),
)
# Carl Roth prints the supplier block with no label at all, so fall back to
# the first line that ends in a company legal form ("Carl Roth GmbH + Co KG").
_LEGAL_FORM_LINE_RE = re.compile(
    r"^(.{2,80}?\b(?:GmbH(?:\s*\+\s*Co\.?\s*KG)?|AG|KG|Ltd\.?|Limited|Inc\.?|LLC|"
    r"S\.?\s?L\.?\s?U\.?|S\.A\.?|plc|B\.V\.|Corp\.?|Corporation))[ \t]*$",
    re.MULTILINE,
)
# PanReac puts phone/fax on the same line as the company name.
_TRAILING_CONTACT_RE = re.compile(r"\s+(?:Tel|Phone|Fax)\.?\s.*$", re.IGNORECASE)


def _first_match(patterns, text: str) -> str | None:
    """Return the first capture group of the first pattern that matches."""
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None


def _parse_supplier(section1_text: str) -> str | None:
    """Find the supplier name across the label styles real SDSs use."""
    supplier = _first_match(_SUPPLIER_LABEL_PATTERNS, section1_text)
    if supplier is None:
        legal = _LEGAL_FORM_LINE_RE.search(section1_text)
        supplier = legal.group(1).strip() if legal else None
    if supplier:
        supplier = _TRAILING_CONTACT_RE.sub("", supplier).strip()
    return supplier or None


def build_metadata_from_section1(
    section1_text: str,
    document_id: str,
    source_path: str,
) -> SDSMetadata:
    """Parse minimal document metadata out of an SDS's Section 1 text.

    Real SDS Section 1 text is field-labelled rather than free prose, so a
    handful of targeted regexes are enough here -- this is a much easier
    extraction problem than Section 7-10's value extraction, which is why it
    lives here rather than in `extraction/value_extractor.py`.

    Falls back to placeholder values when a field can't be found, rather than
    raising -- a missing chemical name shouldn't block ingesting the rest of
    the document's extractable safety values.

    Args:
        section1_text: Raw text of GHS Section 1 (Identification).
        document_id: Identifier to assign this document (e.g. source filename).
        source_path: Where this document came from, for provenance.

    Returns:
        SDSMetadata with whatever fields could be parsed.
    """
    cas_match = _CAS_NUMBER_RE.search(section1_text)
    chemical_name = _first_match(_PRODUCT_NAME_PATTERNS, section1_text) or "unknown"
    supplier = _parse_supplier(section1_text) or "unknown"

    return SDSMetadata(
        document_id=document_id,
        chemical_name=chemical_name,
        cas_number=cas_match.group(1) if cas_match else None,
        supplier=supplier,
        retrieval_date=date.today(),
        source_url=source_path,
    )


# ---------------------------------------------------------------------------
# Combined loader
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Admin metadata overrides (persisted beside the PDF)
# ---------------------------------------------------------------------------

_OVERRIDE_FIELDS = ("chemical_name", "supplier")
MAX_OVERRIDE_LENGTH = 200


def override_path_for(pdf_path: Path) -> Path:
    """Sidecar file holding admin overrides for one PDF ("<id>.meta.json")."""
    return pdf_path.with_suffix(".meta.json")


def write_metadata_overrides(pdf_path: Path, overrides: dict[str, str]) -> None:
    """Persist admin-supplied chemical name / supplier for an uploaded PDF.

    Why a sidecar file rather than only patching the in-memory metadata: the
    corpus is rebuilt from disk on every restart, which re-parses Section 1
    and would silently discard an admin's correction (e.g. a Carl Roth SDS
    whose name the parser can't read). Writing it beside the PDF keeps the
    PDF itself untouched -- the cited source stays byte-identical to what
    the supplier published.
    """
    data = {
        k: v.strip()
        for k, v in overrides.items()
        if k in _OVERRIDE_FIELDS and v and v.strip()
    }
    if not data:
        return
    target = override_path_for(pdf_path)
    tmp = target.with_name(target.name + ".part")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(target)


def _apply_metadata_overrides(pdf_path: Path, metadata: SDSMetadata) -> None:
    """Apply a sidecar's overrides, ignoring anything malformed.

    A corrupt or hand-edited sidecar must never stop the corpus loading --
    the parsed Section 1 values are used instead.
    """
    sidecar = override_path_for(pdf_path)
    if not sidecar.is_file():
        return
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(data, dict):
        return
    for field in _OVERRIDE_FIELDS:
        value = data.get(field)
        if (
            isinstance(value, str)
            and value.strip()
            and len(value) <= MAX_OVERRIDE_LENGTH
        ):
            setattr(metadata, field, value.strip())


def load_sds_pdf(path: Path) -> tuple[str, SDSMetadata]:
    """Load a local SDS PDF: extract its text and parse minimal metadata.

    Args:
        path: Path to a local SDS PDF (typically under `corpus/raw/`).

    Returns:
        Tuple of (raw_text, SDSMetadata) -- raw_text feeds
        `extraction.pipeline.extract_document()`, metadata carries provenance.
        Admin overrides saved beside the PDF (see `write_metadata_overrides`)
        take precedence over the parsed Section 1 values.
    """
    raw_text = extract_text_from_pdf(path)
    section1_text = split_sections(raw_text).sections.get(1, raw_text[:2000])
    metadata = build_metadata_from_section1(
        section1_text,
        document_id=path.stem,
        source_path=str(path),
    )
    _apply_metadata_overrides(path, metadata)
    return raw_text, metadata


def load_all_local_pdfs(raw_dir: Path) -> list[tuple[str, SDSMetadata]]:
    """Load every PDF in a directory (e.g. `corpus/raw/`).

    Args:
        raw_dir: Directory containing local SDS PDFs.

    Returns:
        List of (raw_text, SDSMetadata) tuples, one per PDF found.
    """
    return [load_sds_pdf(p) for p in sorted(raw_dir.glob("*.pdf"))]
