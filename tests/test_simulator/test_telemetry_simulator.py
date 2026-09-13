"""Unit tests for the telemetry simulator's reading-generation logic (M4).

`TelemetryPublisher` itself is not exercised here -- its constructor
eagerly opens a real TLS MQTT connection, which has no place in CI.
`generate_reading` is the pure, broker-free part, and is proven here to
actually drive a genuine WARNING through the real monitor pipeline in
excursion mode -- not just to produce "a big number".
"""

from datetime import date

from agents.agent_a_retrieval.corpus_retrieval import CorpusRetriever
from agents.agent_c_environment.monitor import EnvironmentalMonitor
from agents.protocols.schemas import SafetyState
from extraction.models import SDSMetadata
from extraction.pipeline import extract_document
from safety.state_machine import DeterministicSafetyEvaluator
from simulator.telemetry_simulator import (
    _STEADY_HUMIDITY_RANGE_PCT,
    _STEADY_TEMP_RANGE_C,
    generate_reading,
)


def test_steady_mode_stays_within_documented_ambient_ranges() -> None:
    for _ in range(20):
        reading = generate_reading("Zone_A", "steady", "device1")
        assert (
            _STEADY_TEMP_RANGE_C[0]
            <= reading.temperature_celsius
            <= _STEADY_TEMP_RANGE_C[1]
        )
        assert (
            _STEADY_HUMIDITY_RANGE_PCT[0]
            <= reading.humidity_percent
            <= _STEADY_HUMIDITY_RANGE_PCT[1]
        )


def test_generated_reading_matches_requested_zone_and_device() -> None:
    reading = generate_reading("Zone_B", "steady", "esp32-007")
    assert reading.zone_id == "Zone_B"
    assert reading.device_id == "esp32-007"


def test_excursion_mode_produces_a_genuine_warning_for_zone_with_real_threshold() -> (
    None
):
    """The claim this guards: excursion mode isn't just "a big number" --
    fed through the real retrieval + deterministic-safety-layer pipeline for
    a chemical this corpus actually has a threshold for, it produces a real,
    evidence-backed WARNING."""
    doc = extract_document(
        "SECTION 7: Handling and storage\nRecommended storage temperature : 2 - 8 \xb0C\n",
        SDSMetadata(
            document_id="doc_h2o2",
            chemical_name="Hydrogen peroxide solution",
            supplier="Test Supplier",
            retrieval_date=date.today(),
        ),
    )
    monitor = EnvironmentalMonitor(
        CorpusRetriever([doc]),
        DeterministicSafetyEvaluator(),
        {"Zone_C": ["Hydrogen peroxide solution"]},
    )

    reading = generate_reading("Zone_C", "excursion", "device1")
    evaluation = monitor.handle_reading(reading)

    assert evaluation.aggregated_state == SafetyState.WARNING
    assert evaluation.is_excursion is True
