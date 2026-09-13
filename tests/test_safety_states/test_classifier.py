"""Unit tests for HazardSeverityClassifier (Lab 08)."""

import pytest

from agents.agent_b_analysis.classifier import (
    HazardSeverityClassifier,
    compare_balanced_vs_unbalanced_minority_f1,
)


@pytest.fixture
def classifier() -> HazardSeverityClassifier:
    clf = HazardSeverityClassifier()
    clf.train_synthetic_baseline()
    return clf


def test_classifier_training_report(classifier: HazardSeverityClassifier) -> None:
    res = classifier.train_synthetic_baseline()
    assert "report" in res
    assert classifier.is_trained is True


def test_predict_severity_low(classifier: HazardSeverityClassifier) -> None:
    severity, confidence = classifier.predict_severity(
        nfpa_health=0, nfpa_flammability=0, nfpa_instability=0, ghs_code_count=0
    )
    assert severity == "LOW"
    assert confidence > 0.0


def test_predict_severity_critical(classifier: HazardSeverityClassifier) -> None:
    severity, confidence = classifier.predict_severity(
        nfpa_health=4, nfpa_flammability=4, nfpa_instability=3, ghs_code_count=7
    )
    assert severity == "CRITICAL"
    assert confidence > 0.0


def test_training_data_is_imbalanced_not_evenly_split() -> None:
    """Regression guard for the bug this module was built to fix: the
    original 8-row dataset had exactly 2 samples per class, which made
    class_weight="balanced" a no-op -- there was no imbalance to correct
    for. The plan's own justification for balanced weighting ("critical
    hazards are rare by definition") requires a genuinely imbalanced
    class distribution to be a meaningful claim at all."""
    from agents.agent_b_analysis.classifier import _Y_TRAIN

    counts = {label: int((_Y_TRAIN == label).sum()) for label in range(4)}
    assert len(set(counts.values())) > 1, "class counts must not all be equal"
    assert counts[3] < counts[0], "CRITICAL (rare) must have fewer samples than LOW"


def test_balanced_weighting_improves_critical_class_recall() -> None:
    """The named plan deliverable (Part VIII item 20): balanced vs.
    unbalanced minority-class F1, evaluated via cross-validation (not the
    training set, which an unconstrained-enough tree can memorise either
    way) so the comparison reflects held-out behaviour."""
    result = compare_balanced_vs_unbalanced_minority_f1()

    assert result["balanced_mean_critical_f1"] > result["unbalanced_mean_critical_f1"]
