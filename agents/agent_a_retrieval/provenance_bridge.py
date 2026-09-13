"""Bridges extraction-layer provenance into the safety-evaluation model (M2).

`extraction.models.ExtractionResult` (M1's output) and
`agents.protocols.schemas.ProvenancedThreshold` (what `safety/state_machine.py`
and `api/main.py` actually consume) were built independently and never
connected -- confirmed by grep: no file in the repository imported both.
That meant "full provenance on every claim" (plan §9) was only ever true
inside the unwired extraction layer, never on the live safety-evaluation
path. This module is that missing connection.

Not every ExtractionResult converts. A "threshold" needs a direction (is the
value a ceiling or a floor the observed condition is compared against) and a
numeric value -- CAS numbers, H/P-codes, PPE requirements, and
incompatibility lists are all real extracted claims but none of them are
safety thresholds in that sense, so they're deliberately excluded rather
than forced into a shape that doesn't fit.
"""

from __future__ import annotations

from agents.protocols.schemas import ProvenancedThreshold, ThresholdDirection
from extraction.models import ClaimType, ExtractionResult
from safety.provenance import build_citation_string, resolve_supplier_authority

# Which extracted claim types are genuine thresholds, and which direction
# each one represents. Exposure limits, flash point, and boiling point are
# all "must not exceed" ceilings from a safety standpoint (approaching a
# flash point while handling a solvent is a fire risk), so they map to MAX
# alongside the explicit storage-temperature-max/humidity-max claims.
_THRESHOLD_CLAIM_TYPES: dict[ClaimType, tuple[str, ThresholdDirection]] = {
    ClaimType.STORAGE_TEMP_MAX: ("max_storage_temperature", ThresholdDirection.MAX),
    ClaimType.STORAGE_TEMP_MIN: ("min_storage_temperature", ThresholdDirection.MIN),
    ClaimType.STORAGE_HUMIDITY_MAX: ("max_storage_humidity", ThresholdDirection.MAX),
    ClaimType.EXPOSURE_TWA: ("exposure_twa", ThresholdDirection.MAX),
    ClaimType.EXPOSURE_STEL: ("exposure_stel", ThresholdDirection.MAX),
    ClaimType.FLASH_POINT: ("flash_point", ThresholdDirection.MAX),
    ClaimType.BOILING_POINT: ("boiling_point", ThresholdDirection.MAX),
}


def to_provenanced_threshold(result: ExtractionResult) -> ProvenancedThreshold | None:
    """Convert one ExtractionResult into a ProvenancedThreshold, if it is one.

    Args:
        result: A single extracted claim (from extraction.pipeline.extract_document).

    Returns:
        A ProvenancedThreshold carrying the full provenance chain through to
        the safety-evaluation path, or None if this claim type isn't a
        numeric threshold (e.g. PPE_REQUIREMENT, CAS_NUMBER, H_CODE) or its
        value isn't parseable as a number.
    """
    mapping = _THRESHOLD_CLAIM_TYPES.get(result.claim_type)
    if mapping is None:
        return None

    metric_name, direction = mapping
    try:
        value = float(result.value)
    except (TypeError, ValueError):
        return None

    # Normalise "\xb0C"/"\xb0F" (extraction's format, matching how the value
    # is literally written in the source document) down to "C"/"F" -- the
    # convention every other unit string in this codebase already uses
    # (SafetyEvaluationRequest payloads, every existing ProvenancedThreshold
    # construction site). safety/state_machine.py compares units by exact
    # string equality (by design -- it refuses to silently assume a
    # conversion), so leaving the degree sign in would make every real
    # temperature threshold spuriously fail as a "unit mismatch" against a
    # request sent in plain "C". Only ever strips a leading degree sign;
    # non-temperature units (%, ppm, mg/m3) pass through unchanged.
    unit = result.unit.lstrip("\xb0")

    citation = build_citation_string(
        chemical_name=result.chemical,
        sds_id=result.document_id,
        supplier_name=result.supplier,
        section_number=f"Section {result.section_number}",
        metric_name=metric_name,
        value=value,
        unit=unit,
    )

    return ProvenancedThreshold(
        metric_name=metric_name,
        value=value,
        unit=unit,
        direction=direction,
        sds_id=result.document_id,
        supplier_name=result.supplier,
        section_number=f"Section {result.section_number}",
        authority_score=resolve_supplier_authority(result.supplier),
        citation=citation,
        sds_revision=result.sds_revision,
        revision_date=result.revision_date,
        page_number=result.page_number,
        original_text_span=result.original_text_span,
        extraction_method=result.extraction_method,
        confidence=result.confidence,
        source_authority=result.source_authority,
    )


def convert_all(results: list[ExtractionResult]) -> list[ProvenancedThreshold]:
    """Convert a list of ExtractionResults, silently skipping non-thresholds.

    Args:
        results: Extracted claims for one or more documents.

    Returns:
        ProvenancedThreshold list -- shorter than `results` whenever some
        claims aren't threshold-shaped (see `to_provenanced_threshold`).
    """
    converted = (to_provenanced_threshold(result) for result in results)
    return [threshold for threshold in converted if threshold is not None]
