"""Unit tests for the MQTT subscriber's message-handling logic (Agent C, M4).

None of these tests touch a real broker or TLS certs -- `handle_raw_message`
is exercised directly (paho invokes the exact same method internally), and
`MqttEnvironmentSubscriber.__init__` itself is not exercised here since it
eagerly calls `tls_set()` against real cert files that don't exist in CI.
"""

import json
from datetime import date, datetime, timezone

import pytest

from agents.agent_a_retrieval.corpus_retrieval import CorpusRetriever
from agents.agent_c_environment.monitor import EnvironmentalMonitor
from agents.agent_c_environment.mqtt_subscriber import (
    evaluate_raw_message,
    parse_reading,
    topic_for_zone,
    zone_id_from_topic,
)
from agents.protocols.schemas import SafetyState
from extraction.models import SDSMetadata
from extraction.pipeline import extract_document
from safety.state_machine import DeterministicSafetyEvaluator


def test_topic_for_zone_round_trips_with_zone_id_from_topic() -> None:
    topic = topic_for_zone("Zone_C")
    assert topic == "chemsentry/sensors/Zone_C/reading"
    assert zone_id_from_topic(topic) == "Zone_C"


@pytest.mark.parametrize(
    "topic",
    [
        "chemsentry/sensors/Zone_C/other",
        "chemsentry/alerts/Zone_C/reading",
        "chemsentry/sensors/reading",
        "totally/unrelated/topic",
    ],
)
def test_zone_id_from_topic_rejects_non_matching_topics(topic: str) -> None:
    assert zone_id_from_topic(topic) is None


def _valid_payload() -> dict:
    return {
        "zone_id": "Zone_C",
        "temperature_celsius": 5.0,
        "humidity_percent": 40.0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "device_id": "esp32-test",
    }


def test_parse_reading_accepts_valid_json_payload() -> None:
    reading = parse_reading(json.dumps(_valid_payload()).encode())
    assert reading is not None
    assert reading.zone_id == "Zone_C"
    assert reading.temperature_celsius == 5.0


def test_parse_reading_rejects_malformed_json() -> None:
    assert parse_reading(b"not json at all") is None


def test_parse_reading_rejects_out_of_range_temperature() -> None:
    """DHT22's real sensing range is -40 to 80 C -- a payload outside that
    is not a plausible real reading and must be dropped, not silently
    accepted (SensorReading's Field(ge=-40, le=80) enforces this)."""
    bad = _valid_payload()
    bad["temperature_celsius"] = 999.0
    assert parse_reading(json.dumps(bad).encode()) is None


def test_parse_reading_rejects_missing_required_field() -> None:
    bad = _valid_payload()
    del bad["device_id"]
    assert parse_reading(json.dumps(bad).encode()) is None


def _make_monitor() -> EnvironmentalMonitor:
    doc = extract_document(
        "SECTION 7: Handling and storage\nRecommended storage temperature : 2 - 8 \xb0C\n",
        SDSMetadata(
            document_id="doc_h2o2",
            chemical_name="Hydrogen peroxide solution",
            supplier="Test Supplier",
            retrieval_date=date.today(),
        ),
    )
    retriever = CorpusRetriever([doc])
    evaluator = DeterministicSafetyEvaluator()
    return EnvironmentalMonitor(
        retriever, evaluator, {"Zone_C": ["Hydrogen peroxide solution"]}
    )


def test_evaluate_raw_message_dispatches_to_monitor_and_returns_evaluation() -> None:
    monitor = _make_monitor()
    payload = json.dumps(_valid_payload()).encode()

    evaluation = evaluate_raw_message(monitor, topic_for_zone("Zone_C"), payload)

    assert evaluation is not None
    assert evaluation.zone_id == "Zone_C"
    assert evaluation.aggregated_state == SafetyState.SAFE


def test_evaluate_raw_message_invokes_on_excursion_only_for_real_warnings() -> None:
    monitor = _make_monitor()
    excursions = []

    safe_payload = _valid_payload()
    evaluate_raw_message(
        monitor,
        topic_for_zone("Zone_C"),
        json.dumps(safe_payload).encode(),
        on_excursion=excursions.append,
    )
    assert excursions == []

    warning_payload = _valid_payload()
    warning_payload["temperature_celsius"] = 20.0
    evaluate_raw_message(
        monitor,
        topic_for_zone("Zone_C"),
        json.dumps(warning_payload).encode(),
        on_excursion=excursions.append,
    )
    assert len(excursions) == 1
    assert excursions[0].aggregated_state == SafetyState.WARNING


def test_evaluate_raw_message_returns_none_for_unrecognised_topic() -> None:
    monitor = _make_monitor()
    result = evaluate_raw_message(
        monitor, "foo/bar", json.dumps(_valid_payload()).encode()
    )
    assert result is None


def test_evaluate_raw_message_returns_none_for_malformed_payload() -> None:
    monitor = _make_monitor()
    result = evaluate_raw_message(monitor, topic_for_zone("Zone_C"), b"not json")
    assert result is None
