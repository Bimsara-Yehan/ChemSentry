"""Unit tests for HazardSeverityClassifier (Lab 08)."""

import pytest
from agents.agent_b_analysis.classifier import HazardSeverityClassifier


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
