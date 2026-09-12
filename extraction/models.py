"""Core data models for the ChemSentry extraction and indexing pipeline.

Every safety-related claim must carry full provenance (plan §9). These models
enforce that contract at the type level — if a field is missing, Pydantic raises
before the data reaches downstream consumers.

Used by:
    - extraction/ (M1) — produces ExtractionResult and ProcessedDocument
    - indexing/ (M1)   — indexes ProcessedDocument.tokens
    - agents/agent_a_retrieval/ (M2) — reads provenance on retrieved evidence
    - agents/agent_b_analysis/ (M3)  — reads SDSMetadata for conflict detection

Design decision: Pydantic v2 BaseModel for runtime validation and JSON
serialisation. We deliberately avoid dataclasses because the downstream API
layer (FastAPI) already uses Pydantic, and keeping one model system avoids
translation bugs.
"""

from __future__ import annotations

import uuid
from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SourceAuthority(str, Enum):
    """Source authority hierarchy (plan §7).

    Retrieval prefers different sources for different question types.
    This enum tags each extraction so downstream can apply the preference table.
    """

    SUPPLIER_SDS = "supplier_sds"
    NIOSH = "niosh"
    PUBCHEM = "pubchem"
    CAMEO = "cameo"
    US_CSB = "us_csb"  # US Chemical Safety Board — incident data


class ClaimType(str, Enum):
    """The kind of safety claim extracted from the document.

    Typed so that downstream code can switch on claim type without string
    matching, and so new claim types are a visible code change (not a silent
    typo in a string literal).
    """

    STORAGE_TEMP_MAX = "storage_temperature_max"
    STORAGE_TEMP_MIN = "storage_temperature_min"
    STORAGE_HUMIDITY_MAX = "storage_humidity_max"
    EXPOSURE_TWA = "exposure_twa"
    EXPOSURE_STEL = "exposure_stel"
    PPE_REQUIREMENT = "ppe_requirement"
    INCOMPATIBILITY = "incompatibility"
    FLASH_POINT = "flash_point"
    BOILING_POINT = "boiling_point"
    H_CODE = "h_code"
    P_CODE = "p_code"
    CAS_NUMBER = "cas_number"
    CHEMICAL_FORMULA = "chemical_formula"
    GHS_CLASSIFICATION = "ghs_classification"


class ExtractionMethod(str, Enum):
    """How a value was extracted — provenance for the extraction step itself."""

    REGEX = "regex"
    STRUCTURED_FIELD = "structured_field"  # e.g. a clearly labelled table cell


# ---------------------------------------------------------------------------
# Document-level metadata
# ---------------------------------------------------------------------------

class SDSMetadata(BaseModel):
    """Versioning metadata for a single Safety Data Sheet (plan §10).

    Tracks: chemical · supplier · sds_version · revision_date · retrieval_date.
    Retrieval prefers current versions; version disagreements are conflicts.
    """

    document_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for this specific document instance.",
    )
    chemical_name: str = Field(
        ..., description="Primary chemical name as stated on the SDS."
    )
    cas_number: Optional[str] = Field(
        default=None, description="CAS registry number, e.g. '108-88-3'."
    )
    supplier: str = Field(
        ..., description="Supplier / manufacturer who issued this SDS."
    )
    sds_version: str = Field(
        default="unknown", description="Version string from the SDS itself."
    )
    revision_date: Optional[date] = Field(
        default=None, description="Date the SDS was last revised by the supplier."
    )
    retrieval_date: date = Field(
        default_factory=date.today,
        description="Date we downloaded or ingested this document.",
    )
    source_url: str = Field(
        default="", description="URL from which this SDS was retrieved."
    )
    source_authority: SourceAuthority = Field(
        default=SourceAuthority.SUPPLIER_SDS,
        description="Which tier in the source authority hierarchy (plan §7).",
    )


# ---------------------------------------------------------------------------
# Extraction-level provenance
# ---------------------------------------------------------------------------

class ExtractionResult(BaseModel):
    """A single extracted value with full provenance (plan §9).

    Every safety-related claim carries:
        chemical · claim · document_id · supplier · sds_revision ·
        revision_date · section_number · page_number · original_text_span ·
        extraction_method · confidence · source_authority

    This is the atomic unit of evidence that flows through the entire system.
    """

    chemical: str
    claim_type: ClaimType
    value: str = Field(
        ..., description="Extracted value, e.g. '25' or 'nitrile gloves'."
    )
    unit: str = Field(
        default="",
        description="Unit of the value, e.g. '°C', 'ppm', 'mg/m³', or '' for text.",
    )
    document_id: str
    supplier: str
    sds_revision: str = Field(default="unknown")
    revision_date: Optional[date] = Field(default=None)
    section_number: int = Field(
        ..., ge=1, le=16, description="GHS section number (1–16)."
    )
    page_number: Optional[int] = Field(default=None)
    original_text_span: str = Field(
        ...,
        description="Exact text span from the document that the regex matched.",
    )
    extraction_method: ExtractionMethod = Field(default=ExtractionMethod.REGEX)
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Extraction confidence score."
    )
    source_authority: SourceAuthority = Field(
        default=SourceAuthority.SUPPLIER_SDS,
    )


# ---------------------------------------------------------------------------
# Fully processed document — ready for indexing
# ---------------------------------------------------------------------------

class ProcessedDocument(BaseModel):
    """A fully processed SDS document, ready for indexing.

    Bundles metadata, raw section text, extracted values, and preprocessed
    tokens into a single serialisable object.  The indexing layer consumes
    this to build inverted, positional, and k-gram indexes.
    """

    metadata: SDSMetadata
    sections: dict[int, str] = Field(
        default_factory=dict,
        description="section_number → raw section text after splitting.",
    )
    extractions: list[ExtractionResult] = Field(
        default_factory=list,
        description="All values extracted from this document.",
    )
    tokens: list[str] = Field(
        default_factory=list,
        description="Preprocessed tokens (after tokenise → stop words → stem).",
    )
