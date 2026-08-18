"""Unit tests for evidence reconciler and conflict detection (M3)."""

import pytest

from agents.agent_b_analysis.reconciler import EvidenceReconciler
from agents.protocols.schemas import ProvenancedThreshold, ThresholdDirection


@pytest.fixture
def reconciler() -> EvidenceReconciler:
    return EvidenceReconciler()


def test_jaccard_similarity_exact_match(reconciler: EvidenceReconciler) -> None:
    set1 = {"H225", "H319", "H336"}
    set2 = {"H225", "H319", "H336"}
    assert reconciler.jaccard_similarity(set1, set2) == 1.0


def test_jaccard_similarity_partial_match(reconciler: EvidenceReconciler) -> None:
    set1 = {"H225", "H319", "H336"}
    set2 = {"H225", "H319"}
    # intersection=2, union=3 -> 2/3 = 0.6667
    sim = reconciler.jaccard_similarity(set1, set2)
    assert pytest.approx(sim, 0.01) == 0.6667


def test_jaccard_similarity_both_empty(reconciler: EvidenceReconciler) -> None:
    """Two empty hazard sets have no shared evidence, so similarity is 0.0, not 1.0."""
    assert reconciler.jaccard_similarity(set(), set()) == 0.0


def test_detect_hazard_conflicts(reconciler: EvidenceReconciler) -> None:
    set_a = {"H225", "H319", "H336"}
    set_b = {"H314", "H410"}
    has_conflict, sim_score, explanation = reconciler.detect_hazard_conflicts(
        set_a, set_b, min_jaccard_threshold=0.5
    )

    assert has_conflict is True
    assert sim_score == 0.0
    assert "conflict" in explanation.lower()


def test_detect_hazard_conflicts_both_empty_is_not_alignment(
    reconciler: EvidenceReconciler,
) -> None:
    """A dual extraction failure (no hazards from either source) must not read as agreement."""
    has_conflict, _sim_score, explanation = reconciler.detect_hazard_conflicts(
        set(), set()
    )

    assert has_conflict is True
    assert "no hazard statements" in explanation.lower()


def test_select_authoritative_threshold(reconciler: EvidenceReconciler) -> None:
    t_primary = ProvenancedThreshold(
        metric_name="max_temp",
        value=25.0,
        unit="C",
        direction=ThresholdDirection.MAX,
        sds_id="SDS-1",
        supplier_name="Primary Mfg",
        authority_score=1.0,
        citation="Cit 1",
    )
    t_distributor = ProvenancedThreshold(
        metric_name="max_temp",
        value=30.0,
        unit="C",
        direction=ThresholdDirection.MAX,
        sds_id="SDS-2",
        supplier_name="Distributor",
        authority_score=0.85,
        citation="Cit 2",
    )

    primary, notes = reconciler.select_authoritative_threshold(
        [t_distributor, t_primary]
    )
    assert primary.supplier_name == "Primary Mfg"
    assert primary.authority_score == 1.0
    assert len(notes) == 2


def test_select_authoritative_threshold_flags_equal_authority_conflict(
    reconciler: EvidenceReconciler,
) -> None:
    """Two equal-authority sources diverging beyond tolerance must not silently pick a 'primary'."""
    t_a = ProvenancedThreshold(
        metric_name="max_temp",
        value=25.0,
        unit="C",
        direction=ThresholdDirection.MAX,
        sds_id="SDS-1",
        supplier_name="Primary Mfg A",
        authority_score=1.0,
        citation="Cit 1",
    )
    t_b = ProvenancedThreshold(
        metric_name="max_temp",
        value=100.0,
        unit="C",
        direction=ThresholdDirection.MAX,
        sds_id="SDS-2",
        supplier_name="Primary Mfg B",
        authority_score=1.0,
        citation="Cit 2",
    )

    primary, notes = reconciler.select_authoritative_threshold([t_a, t_b])
    assert primary is None
    assert any("conflict" in note.lower() for note in notes)
