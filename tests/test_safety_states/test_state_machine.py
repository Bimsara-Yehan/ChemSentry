"""Unit tests for deterministic safety state machine (M3)."""

import pytest

from agents.protocols.schemas import (
    ProvenancedThreshold,
    SafetyEvaluationRequest,
    SafetyState,
    ThresholdDirection,
)
from safety.provenance import build_citation_string, resolve_supplier_authority
from safety.state_machine import DeterministicSafetyEvaluator


@pytest.fixture
def evaluator() -> DeterministicSafetyEvaluator:
    return DeterministicSafetyEvaluator(conflict_tolerance_pct=5.0)


@pytest.fixture
def sample_threshold() -> ProvenancedThreshold:
    return ProvenancedThreshold(
        metric_name="max_storage_temperature",
        value=25.0,
        unit="C",
        direction=ThresholdDirection.MAX,
        sds_id="SDS-ACETONE-2026-V1",
        supplier_name="Sigma-Aldrich",
        section_number="Section 7",
        authority_score=1.0,
        citation="[SDS-ACETONE-2026-V1] Section 7 - Sigma-Aldrich: max_storage_temperature threshold = 25.0 C",
    )


def test_evaluate_safe_state(
    evaluator: DeterministicSafetyEvaluator, sample_threshold: ProvenancedThreshold
) -> None:
    """Reading below threshold must return SAFE."""
    request = SafetyEvaluationRequest(
        chemical_name="Acetone",
        cas_number="67-64-1",
        zone_id="Zone-A",
        metric_name="max_storage_temperature",
        current_value=21.5,
        unit="C",
    )
    result = evaluator.evaluate(request, [sample_threshold])

    assert result.state == SafetyState.SAFE
    assert result.current_value == 21.5
    assert result.threshold_value == 25.0
    assert result.provenance is not None
    assert result.provenance.sds_id == "SDS-ACETONE-2026-V1"
    assert "strictly below" in result.reasoning


def test_evaluate_warning_state(
    evaluator: DeterministicSafetyEvaluator, sample_threshold: ProvenancedThreshold
) -> None:
    """Reading meeting or exceeding threshold must return WARNING."""
    request = SafetyEvaluationRequest(
        chemical_name="Acetone",
        cas_number="67-64-1",
        zone_id="Zone-A",
        metric_name="max_storage_temperature",
        current_value=26.2,
        unit="C",
    )
    result = evaluator.evaluate(request, [sample_threshold])

    assert result.state == SafetyState.WARNING
    assert result.current_value == 26.2
    assert result.threshold_value == 25.0
    assert "meets or exceeds" in result.reasoning


def test_evaluate_unknown_when_no_thresholds(
    evaluator: DeterministicSafetyEvaluator,
) -> None:
    """Empty threshold list must return UNKNOWN."""
    request = SafetyEvaluationRequest(
        chemical_name="Unknown-Chem",
        cas_number=None,
        zone_id="Zone-B",
        metric_name="max_storage_temperature",
        current_value=20.0,
        unit="C",
    )
    result = evaluator.evaluate(request, [])

    assert result.state == SafetyState.UNKNOWN
    assert result.threshold_value is None
    assert "UNKNOWN: No versioned SDS threshold retrieved" in result.reasoning


def test_evaluate_unknown_on_conflicting_equal_authority_suppliers(
    evaluator: DeterministicSafetyEvaluator,
) -> None:
    """Equal authority suppliers with conflicting values (>5% variance) must return UNKNOWN."""
    t1 = ProvenancedThreshold(
        metric_name="max_storage_temperature",
        value=25.0,
        unit="C",
        direction=ThresholdDirection.MAX,
        sds_id="SDS-ACETONE-SUPPLIER-A",
        supplier_name="Supplier A",
        authority_score=1.0,
        citation="Supplier A SDS",
    )
    t2 = ProvenancedThreshold(
        metric_name="max_storage_temperature",
        value=35.0,  # 40% variance vs 25.0 C
        unit="C",
        direction=ThresholdDirection.MAX,
        sds_id="SDS-ACETONE-SUPPLIER-B",
        supplier_name="Supplier B",
        authority_score=1.0,
        citation="Supplier B SDS",
    )

    request = SafetyEvaluationRequest(
        chemical_name="Acetone",
        zone_id="Zone-A",
        metric_name="max_storage_temperature",
        current_value=28.0,
        unit="C",
    )
    result = evaluator.evaluate(request, [t1, t2])

    assert result.state == SafetyState.UNKNOWN
    assert "diverge beyond" in result.reasoning


def test_evaluate_unknown_on_third_equal_authority_outlier(
    evaluator: DeterministicSafetyEvaluator,
) -> None:
    """A conflict among 3+ equal-authority sources must be caught, not just the top two."""

    def make_threshold(supplier: str, value: float) -> ProvenancedThreshold:
        return ProvenancedThreshold(
            metric_name="max_storage_temperature",
            value=value,
            unit="C",
            direction=ThresholdDirection.MAX,
            sds_id=f"SDS-{supplier}",
            supplier_name=supplier,
            authority_score=1.0,
            citation=f"{supplier} SDS",
        )

    # Top two (25.0, 26.0) are within 5% tolerance of each other; the third (100.0)
    # is a wild outlier that a top-two-only comparison would never examine.
    thresholds = [
        make_threshold("Supplier A", 25.0),
        make_threshold("Supplier B", 26.0),
        make_threshold("Supplier C", 100.0),
    ]

    request = SafetyEvaluationRequest(
        chemical_name="Acetone",
        zone_id="Zone-A",
        metric_name="max_storage_temperature",
        current_value=28.0,
        unit="C",
    )
    result = evaluator.evaluate(request, thresholds)

    assert result.state == SafetyState.UNKNOWN


def test_evaluate_unknown_on_unit_mismatch(
    evaluator: DeterministicSafetyEvaluator, sample_threshold: ProvenancedThreshold
) -> None:
    """A reading in a different unit than the retrieved threshold must not be compared directly."""
    request = SafetyEvaluationRequest(
        chemical_name="Acetone",
        zone_id="Zone-A",
        metric_name="max_storage_temperature",
        current_value=77.0,
        unit="F",  # sample_threshold is in C
    )
    result = evaluator.evaluate(request, [sample_threshold])

    assert result.state == SafetyState.UNKNOWN
    assert "cannot compare" in result.reasoning.lower()


def test_evaluate_warning_on_min_direction_threshold(
    evaluator: DeterministicSafetyEvaluator,
) -> None:
    """A reading at/below a minimum-floor threshold must be WARNING, not SAFE."""
    min_ventilation = ProvenancedThreshold(
        metric_name="min_ventilation_rate",
        value=10.0,
        unit="m3h",
        direction=ThresholdDirection.MIN,
        sds_id="SDS-VENT-1",
        supplier_name="Sigma-Aldrich",
        authority_score=1.0,
        citation="Sigma-Aldrich ventilation SDS",
    )
    request = SafetyEvaluationRequest(
        chemical_name="Acetone",
        zone_id="Zone-A",
        metric_name="min_ventilation_rate",
        current_value=2.0,  # dangerously low, below the required floor
        unit="m3h",
    )
    result = evaluator.evaluate(request, [min_ventilation])

    assert result.state == SafetyState.WARNING
    assert "is at or below" in result.reasoning


def test_evaluate_unknown_on_hazard_statement_conflict(
    evaluator: DeterministicSafetyEvaluator,
) -> None:
    """Sources that disagree on hazard classification must force UNKNOWN even if values agree."""
    t1 = ProvenancedThreshold(
        metric_name="max_storage_temperature",
        value=25.0,
        unit="C",
        direction=ThresholdDirection.MAX,
        sds_id="SDS-A",
        supplier_name="Supplier A",
        authority_score=1.0,
        citation="Supplier A SDS",
        hazard_statements={"H225", "H319"},
    )
    t2 = ProvenancedThreshold(
        metric_name="max_storage_temperature",
        value=25.5,  # numerically in agreement with t1
        unit="C",
        direction=ThresholdDirection.MAX,
        sds_id="SDS-B",
        supplier_name="Supplier B",
        authority_score=0.85,
        citation="Supplier B SDS",
        hazard_statements={"H314", "H410"},  # but hazard classification disagrees
    )

    request = SafetyEvaluationRequest(
        chemical_name="Acetone",
        zone_id="Zone-A",
        metric_name="max_storage_temperature",
        current_value=20.0,
        unit="C",
    )
    result = evaluator.evaluate(request, [t1, t2])

    assert result.state == SafetyState.UNKNOWN
    assert "hazard statement conflict" in result.reasoning.lower()


def test_provenance_citation_builder() -> None:
    """Test citation string formatting helper."""
    citation = build_citation_string(
        chemical_name="Ethanol",
        sds_id="SDS-ETH-101",
        supplier_name="Merck",
        section_number="Section 7",
        metric_name="flash_point",
        value=13.0,
        unit="C",
    )
    assert (
        citation
        == "[SDS-ETH-101] Section 7 - Merck: Ethanol flash_point threshold = 13.0 C"
    )


def test_authority_resolver() -> None:
    """Test default authority scores."""
    assert resolve_supplier_authority("Primary Manufacturer") == 1.0
    assert resolve_supplier_authority("Authorized Distributor") == 0.85
    assert resolve_supplier_authority("Unknown Supplier") == 0.40


def test_authority_resolver_rejects_out_of_range_custom_score() -> None:
    """Custom authority scores outside [0,1] must raise, matching ProvenancedThreshold's own validation."""
    with pytest.raises(ValueError):
        resolve_supplier_authority("Some Supplier", custom_score=1.5)
