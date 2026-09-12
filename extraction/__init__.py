"""Regex-based section and value extraction from SDS text (M1, Lab 07).

Public API:
    extract_document(raw_text, metadata)  — full pipeline for a single SDS
    split_sections(raw_text)              — GHS section splitting only
    extract_all_from_section(text, ...)   — value extraction from one section
    normalise_value(value, unit, ...)     — unit normalisation only

Data models:
    SDSMetadata, ExtractionResult, ProcessedDocument,
    ClaimType, SourceAuthority, ExtractionMethod
"""

from extraction.models import (
    ClaimType,
    ExtractionMethod,
    ExtractionResult,
    ProcessedDocument,
    SDSMetadata,
    SourceAuthority,
)
from extraction.normaliser import normalise_value
from extraction.pipeline import extract_document
from extraction.section_splitter import split_sections
from extraction.value_extractor import extract_all_from_section

__all__ = [
    "extract_document",
    "split_sections",
    "extract_all_from_section",
    "normalise_value",
    "SDSMetadata",
    "ExtractionResult",
    "ProcessedDocument",
    "ClaimType",
    "SourceAuthority",
    "ExtractionMethod",
]
