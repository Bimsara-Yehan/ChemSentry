"""Unit tests for reconciliation policy governance and configurable thresholds (M3).

Verifies that safety reconciliation thresholds are versioned, documented, and
that modifying the tolerance/cutoff parameters changes the state-machine outcome.
"""

import json
from pathlib import Path

from agents.agent_b_analysis.reconciler import EvidenceReconciler
from agents.protocols.schemas import (
    ProvenancedThreshold,
    SafetyEvaluationRequest,
    SafetyState,
    ThresholdDirection,
)
from safety.reconciliation_policy import (
    CONFLICT_TOLERANCE_PCT,
    DEFAULT_POLICY_PATH,
    HAZARD_JACCARD_THRESHOLD,
    POLICY_CITATION,
    POLICY_RATIONALE,
    POLICY_VERSION,
    load_reconciliation_policy,
    reload_policy,
)
from safety.state_machine import DeterministicSafetyEvaluator


def test_reconciliation_policy_metadata() -> None:
    """Policy constants must carry versioning, rationale, and non-empty citations."""
    assert POLICY_VERSION == "1.0.0"
    assert "ChemSentry Reconciliation Policy" in POLICY_CITATION
    assert len(POLICY_RATIONALE) > 20
    assert CONFLICT_TOLERANCE_PCT == 5.0
    assert HAZARD_JACCARD_THRESHOLD == 0.6
    assert DEFAULT_POLICY_PATH.exists()


def test_conflict_tolerance_parameter_governs_outcome() -> None:
    """Changing conflict_tolerance_pct alters whether equal-authority variance forces UNKNOWN."""
    t_a = ProvenancedThreshold(
        metric_name="flash_point",
        value=100.0,
        unit="C",
        direction=ThresholdDirection.MIN,
        sds_id="SDS-A",
        supplier_name="Supplier A",
        authority_score=1.0,
        citation="SDS-A Sec 9",
    )
    t_b = ProvenancedThreshold(
        metric_name="flash_point",
        value=107.0,  # 7% variance relative to 100
        unit="C",
        direction=ThresholdDirection.MIN,
        sds_id="SDS-B",
        supplier_name="Supplier B",
        authority_score=1.0,
        citation="SDS-B Sec 9",
    )

    request = SafetyEvaluationRequest(
        chemical_name="Toluene",
        zone_id="zone-1",
        metric_name="flash_point",
        current_value=120.0,
        unit="C",
    )

    # 1. Default policy (5% tolerance) -> 7% variance triggers UNKNOWN
    evaluator_strict = DeterministicSafetyEvaluator(conflict_tolerance_pct=5.0)
    result_strict = evaluator_strict.evaluate(request, [t_a, t_b])
    assert result_strict.state == SafetyState.UNKNOWN
    assert "diverge beyond 5.0% tolerance" in result_strict.reasoning
    assert "policy_version=1.0.0" in result_strict.reasoning

    # 2. Relaxed policy (10% tolerance) -> 7% variance is accepted as SAFE (120 > 107)
    evaluator_lenient = DeterministicSafetyEvaluator(conflict_tolerance_pct=10.0)
    result_lenient = evaluator_lenient.evaluate(request, [t_a, t_b])
    assert result_lenient.state == SafetyState.SAFE
    assert "policy_version=1.0.0" in result_lenient.reasoning


def test_hazard_jaccard_threshold_parameter_governs_outcome() -> None:
    """Changing hazard_jaccard_threshold alters whether differing hazard codes force UNKNOWN."""
    # Jaccard = |{"H225"}| / |{"H225", "H302"}| = 1/2 = 0.5
    t_a = ProvenancedThreshold(
        metric_name="storage_temp",
        value=25.0,
        unit="C",
        direction=ThresholdDirection.MAX,
        sds_id="SDS-A",
        supplier_name="Supplier A",
        authority_score=1.0,
        citation="SDS-A Sec 7",
        hazard_statements={"H225", "H302"},
    )
    t_b = ProvenancedThreshold(
        metric_name="storage_temp",
        value=25.0,
        unit="C",
        direction=ThresholdDirection.MAX,
        sds_id="SDS-B",
        supplier_name="Supplier B",
        authority_score=1.0,
        citation="SDS-B Sec 7",
        hazard_statements={"H225"},
    )

    request = SafetyEvaluationRequest(
        chemical_name="Acetone",
        zone_id="zone-2",
        metric_name="storage_temp",
        current_value=20.0,
        unit="C",
    )

    # 1. Default policy (0.6 Jaccard threshold) -> 0.5 similarity triggers UNKNOWN
    evaluator_strict = DeterministicSafetyEvaluator(hazard_jaccard_threshold=0.6)
    result_strict = evaluator_strict.evaluate(request, [t_a, t_b])
    assert result_strict.state == SafetyState.UNKNOWN
    assert "Hazard statement conflict" in result_strict.reasoning

    # 2. Relaxed policy (0.4 Jaccard threshold) -> 0.5 similarity is accepted as SAFE (20 < 25)
    evaluator_lenient = DeterministicSafetyEvaluator(hazard_jaccard_threshold=0.4)
    result_lenient = evaluator_lenient.evaluate(request, [t_a, t_b])
    assert result_lenient.state == SafetyState.SAFE


def test_reconciler_custom_thresholds_directly() -> None:
    """EvidenceReconciler directly honors supplied conflict_tolerance_pct and min_jaccard_threshold."""
    reconciler = EvidenceReconciler()

    # Hazard conflict check with custom threshold
    has_conflict, score, _ = reconciler.detect_hazard_conflicts(
        {"H225", "H302"}, {"H225"}, min_jaccard_threshold=0.4
    )
    assert has_conflict is False
    assert score == 0.5

    has_conflict_strict, score_strict, _ = reconciler.detect_hazard_conflicts(
        {"H225", "H302"}, {"H225"}, min_jaccard_threshold=0.6
    )
    assert has_conflict_strict is True
    assert score_strict == 0.5


def test_custom_policy_file_loading_and_reload(tmp_path: Path) -> None:
    """Loading a custom policy document dynamically changes policy parameters and version tracking."""
    custom_policy_data = {
        "version": "2.0.0-custom",
        "effective_date": "2026-10-01",
        "conflict_tolerance_pct": 15.0,
        "hazard_jaccard_threshold": 0.3,
        "citation": "Custom Safety Policy v2.0.0",
        "rationale": "Special lab environment with relaxed tolerance for testing.",
        "source": "Lab Safety Officer",
    }
    custom_policy_file = tmp_path / "custom_policy.json"
    custom_policy_file.write_text(json.dumps(custom_policy_data), encoding="utf-8")

    # Load custom policy dictionary
    loaded = load_reconciliation_policy(custom_policy_file)
    assert loaded["version"] == "2.0.0-custom"
    assert loaded["conflict_tolerance_pct"] == 15.0

    try:
        # Reload active policy from custom file
        reload_policy(custom_policy_file)
        evaluator = DeterministicSafetyEvaluator()
        assert evaluator.conflict_tolerance_pct == 15.0
        assert evaluator.hazard_jaccard_threshold == 0.3
        assert evaluator.policy_version == "2.0.0-custom"

        # State machine output reflects custom policy version
        t = ProvenancedThreshold(
            metric_name="storage_temp",
            value=25.0,
            unit="C",
            direction=ThresholdDirection.MAX,
            sds_id="SDS-A",
            supplier_name="Supplier A",
            authority_score=1.0,
            citation="SDS-A Sec 7",
        )
        req = SafetyEvaluationRequest(
            chemical_name="Acetone",
            zone_id="Z1",
            metric_name="storage_temp",
            current_value=20.0,
            unit="C",
        )
        res = evaluator.evaluate(req, [t])
        assert res.state == SafetyState.SAFE
        assert "policy_version=2.0.0-custom" in res.reasoning
    finally:
        # Restore default policy
        reload_policy(DEFAULT_POLICY_PATH)
