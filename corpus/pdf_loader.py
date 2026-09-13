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

# Real SDS Section 1 text is field-labelled ("Product name : X"), not prose --
# a much simpler pattern than the Section 7+ value extraction problem.
_PRODUCT_NAME_RE = re.compile(r"Product\s*name\s*:?\s*(.+)", re.IGNORECASE)
_CAS_NUMBER_RE = re.compile(r"CAS[-\s]?No\.?\s*:?\s*(\d{2,7}-\d{2}-\d)", re.IGNORECASE)
_SUPPLIER_RE = re.compile(r"Company\s*:?\s*(.+)", re.IGNORECASE)


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
    name_match = _PRODUCT_NAME_RE.search(section1_text)
    cas_match = _CAS_NUMBER_RE.search(section1_text)
    supplier_match = _SUPPLIER_RE.search(section1_text)

    chemical_name = name_match.group(1).strip() if name_match else "unknown"
    supplier = supplier_match.group(1).strip() if supplier_match else "unknown"

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


def load_sds_pdf(path: Path) -> tuple[str, SDSMetadata]:
    """Load a local SDS PDF: extract its text and parse minimal metadata.

    Args:
        path: Path to a local SDS PDF (typically under `corpus/raw/`).

    Returns:
        Tuple of (raw_text, SDSMetadata) -- raw_text feeds
        `extraction.pipeline.extract_document()`, metadata carries provenance.
    """
    raw_text = extract_text_from_pdf(path)
    section1_text = split_sections(raw_text).sections.get(1, raw_text[:2000])
    metadata = build_metadata_from_section1(
        section1_text,
        document_id=path.stem,
        source_path=str(path),
    )
    return raw_text, metadata


def load_all_local_pdfs(raw_dir: Path) -> list[tuple[str, SDSMetadata]]:
    """Load every PDF in a directory (e.g. `corpus/raw/`).

    Args:
        raw_dir: Directory containing local SDS PDFs.

    Returns:
        List of (raw_text, SDSMetadata) tuples, one per PDF found.
    """
    return [load_sds_pdf(p) for p in sorted(raw_dir.glob("*.pdf"))]
