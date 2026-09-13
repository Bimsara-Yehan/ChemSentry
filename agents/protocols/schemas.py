"""Pydantic schema definitions shared across agents (M2/M3/M4)."""

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional, Set

from pydantic import BaseModel, Field

from extraction.models import ExtractionMethod, SourceAuthority

# Re-exported so existing callers that only import from this module still see
# these two enums here -- ProvenancedThreshold now carries both, and they're
# the same enums extraction/models.py's ExtractionResult uses, not separate
# duplicates, so a value round-trips unchanged through the conversion in
# agents/agent_a_retrieval/provenance_bridge.py.
__all__ = [
    "SafetyState",
    "ThresholdDirection",
    "ProvenancedThreshold",
    "SafetyEvaluationRequest",
    "SafetyEvaluationResult",
    "ExtractionMethod",
    "SourceAuthority",
]


class SafetyState(str, Enum):
    """Deterministic safety state classification (strictly 3 states)."""

    SAFE = "SAFE"
    WARNING = "WARNING"
    UNKNOWN = "UNKNOWN"


class ThresholdDirection(str, Enum):
    """Whether a threshold is a ceiling (max) or a floor (min).

    Required on every ProvenancedThreshold rather than assumed, because a single
    hardcoded ">= means unsafe" comparison would silently invert the verdict for
    minimum-required metrics (e.g. min_ventilation_rate) -- the direction must come
    from the retrieved source document like every other threshold property.
    """

    MAX = "max"
    MIN = "min"


class ProvenancedThreshold(BaseModel):
    """Source-backed threshold retrieved from a versioned SDS document.

    No safety threshold is hardcoded; every threshold is retrieved from a versioned
    source document at query time and cited back to the user.
    """

    metric_name: str = Field(
        description="Name of the safety metric (e.g. max_storage_temperature)"
    )
    value: float = Field(description="Numerical threshold value")
    unit: str = Field(description="Unit of measurement (e.g. C, %, ppm)")
    direction: ThresholdDirection = Field(
        description="Whether 'value' is a maximum ceiling or a minimum floor"
    )
    sds_id: str = Field(description="Versioned SDS document identifier")
    supplier_name: str = Field(description="SDS supplier / manufacturer name")
    section_number: str = Field(default="Section 7", description="SDS section number")
    authority_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Supplier authority weight (0.0 to 1.0)",
    )
    citation: str = Field(
        description="Human-readable citation string citing the source document and section"
    )
    hazard_statements: Optional[Set[str]] = Field(
        default=None,
        description="Hazard statement codes (e.g. H225) extracted alongside this threshold, if any",
    )

    # --- Extraction-layer provenance (plan §9) -----------------------------
    # These mirror extraction.models.ExtractionResult's provenance fields.
    # Added so a claim converted from ExtractionResult (see
    # agents/agent_a_retrieval/provenance_bridge.py) doesn't lose them on the
    # way into the safety-evaluation path -- before this, only sds_id,
    # supplier_name, section_number, authority_score and citation survived,
    # and full per-claim provenance was only ever true inside the
    # unconnected extraction layer, never end-to-end.
    sds_revision: str = Field(
        default="unknown", description="SDS version string (plan §10)"
    )
    revision_date: Optional[date] = Field(
        default=None, description="Date the SDS was last revised by the supplier"
    )
    page_number: Optional[int] = Field(
        default=None, description="Page number the value was extracted from"
    )
    original_text_span: Optional[str] = Field(
        default=None,
        description="Exact source text the extractor matched, for audit/citation",
    )
    extraction_method: Optional[ExtractionMethod] = Field(
        default=None, description="How the underlying value was extracted"
    )
    confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Extraction confidence score"
    )
    source_authority: Optional[SourceAuthority] = Field(
        default=None,
        description=(
            "Which tier of the source authority hierarchy (plan §7) this "
            "claim's document belongs to -- distinct from authority_score, "
            "which weighs supplier trust for conflict tie-breaking"
        ),
    )


class SafetyEvaluationRequest(BaseModel):
    """Request structure for deterministic safety evaluation."""

    chemical_name: str = Field(description="Name of the chemical")
    cas_number: Optional[str] = Field(default=None, description="CAS registry number")
    zone_id: str = Field(description="Monitored environment zone ID")
    metric_name: str = Field(description="Telemetry metric to evaluate")
    current_value: float = Field(description="Current sensor measurement value")
    unit: str = Field(description="Measurement unit")


class SafetyEvaluationResult(BaseModel):
    """Result of deterministic safety evaluation. Strictly SAFE, WARNING, or UNKNOWN."""

    state: SafetyState = Field(description="Deterministic safety verdict")
    chemical_name: str = Field(description="Name of the chemical")
    zone_id: str = Field(description="Monitored environment zone ID")
    metric_name: str = Field(description="Telemetry metric evaluated")
    current_value: float = Field(description="Current sensor reading")
    threshold_value: Optional[float] = Field(
        default=None, description="Retrieved safety threshold value"
    )
    unit: str = Field(description="Measurement unit")
    provenance: Optional[ProvenancedThreshold] = Field(
        default=None, description="Source provenance metadata"
    )
    reasoning: str = Field(
        description="Deterministic reasoning summary explaining the verdict"
    )
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Evaluation timestamp",
    )
