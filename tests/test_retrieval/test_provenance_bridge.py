"""Unit tests for agents/agent_a_retrieval/provenance_bridge.py (M2)."""

from datetime import date

from agents.agent_a_retrieval.provenance_bridge import (
    convert_all,
    to_provenanced_threshold,
)
from agents.protocols.schemas import ThresholdDirection
from extraction.models import (
    ClaimType,
    ExtractionMethod,
    ExtractionResult,
    SourceAuthority,
)


def _extraction_result(**overrides) -> ExtractionResult:
    defaults = dict(
        chemical="Citric acid",
        claim_type=ClaimType.STORAGE_TEMP_MAX,
        value="25",
        unit="\xb0C",
        document_id="c0759",
        supplier="Sigma-Aldrich Chemie GmbH",
        sds_revision="8.2",
        revision_date=date(2026, 8, 23),
        section_number=7,
        page_number=5,
        original_text_span="Recommended storage temperature : 15 - 25 \xb0C",
        extraction_method=ExtractionMethod.REGEX,
        confidence=0.85,
        source_authority=SourceAuthority.SUPPLIER_SDS,
    )
    defaults.update(overrides)
    return ExtractionResult(**defaults)


def test_storage_temp_max_converts_with_max_direction() -> None:
    result = _extraction_result()
    threshold = to_provenanced_threshold(result)

    assert threshold is not None
    assert threshold.metric_name == "max_storage_temperature"
    assert threshold.direction == ThresholdDirection.MAX
    assert threshold.value == 25.0
    assert threshold.unit == "C"


def test_degree_sign_stripped_so_units_match_the_rest_of_the_codebase() -> None:
    """extraction/value_extractor.py produces "\xb0C" (matching the source
    document's literal wording); every existing ProvenancedThreshold in this
    codebase and safety/state_machine.py's exact-string unit comparison both
    use bare "C" -- without normalising here, every real temperature
    threshold would spuriously fail as a "unit mismatch" against a request
    sent in plain "C"."""
    result = _extraction_result(unit="\xb0C")
    threshold = to_provenanced_threshold(result)

    assert threshold is not None
    assert threshold.unit == "C"
    assert "\xb0" not in threshold.citation


def test_storage_temp_min_converts_with_min_direction() -> None:
    result = _extraction_result(claim_type=ClaimType.STORAGE_TEMP_MIN, value="15")
    threshold = to_provenanced_threshold(result)

    assert threshold is not None
    assert threshold.metric_name == "min_storage_temperature"
    assert threshold.direction == ThresholdDirection.MIN


def test_full_provenance_chain_survives_the_conversion() -> None:
    """The fields ProvenancedThreshold was missing before this bridge existed
    must all come through unchanged -- this is the gap the bridge closes."""
    result = _extraction_result()
    threshold = to_provenanced_threshold(result)

    assert threshold is not None
    assert threshold.sds_revision == "8.2"
    assert threshold.revision_date == date(2026, 8, 23)
    assert threshold.page_number == 5
    assert (
        threshold.original_text_span
        == "Recommended storage temperature : 15 - 25 \xb0C"
    )
    assert threshold.extraction_method == ExtractionMethod.REGEX
    assert threshold.confidence == 0.85
    assert threshold.source_authority == SourceAuthority.SUPPLIER_SDS


def test_non_threshold_claim_types_return_none() -> None:
    """PPE requirements, CAS numbers, H/P-codes etc. aren't safety thresholds
    with a direction -- forcing them into ProvenancedThreshold would be
    wrong, not just incomplete."""
    ppe = _extraction_result(
        claim_type=ClaimType.PPE_REQUIREMENT, value="nitrile rubber", unit=""
    )
    cas = _extraction_result(
        claim_type=ClaimType.CAS_NUMBER, value="77-92-9", unit="", confidence=0.95
    )

    assert to_provenanced_threshold(ppe) is None
    assert to_provenanced_threshold(cas) is None


def test_non_numeric_value_returns_none_even_for_a_threshold_claim_type() -> None:
    """Defensive guard: a threshold-shaped claim type whose value somehow
    isn't parseable as a number (e.g. a future extractor bug, or a value
    like "see product label" slipping through) must not crash the bridge or
    silently coerce -- it should just be skipped."""
    result = _extraction_result(value="see product label")

    assert to_provenanced_threshold(result) is None


def test_authority_score_resolved_from_supplier_name() -> None:
    """A real supplier name not in the abstract authority-tier table falls
    back to the documented unrecognized-supplier score, rather than
    silently defaulting to full trust (authority_score=1.0)."""
    result = _extraction_result(supplier="Sigma-Aldrich Chemie GmbH")
    threshold = to_provenanced_threshold(result)

    assert threshold is not None
    assert threshold.authority_score == 0.40


def test_convert_all_filters_out_non_thresholds() -> None:
    results = [
        _extraction_result(claim_type=ClaimType.STORAGE_TEMP_MAX, value="25"),
        _extraction_result(
            claim_type=ClaimType.PPE_REQUIREMENT, value="nitrile", unit=""
        ),
        _extraction_result(claim_type=ClaimType.STORAGE_TEMP_MIN, value="15"),
    ]

    thresholds = convert_all(results)

    assert len(thresholds) == 2
    assert {t.metric_name for t in thresholds} == {
        "max_storage_temperature",
        "min_storage_temperature",
    }
