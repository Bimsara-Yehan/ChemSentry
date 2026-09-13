"""Unit tests for EnvironmentalMonitor (Agent C, M4).

Uses small synthetic SDS text through the real extraction pipeline (same
pattern as tests/test_retrieval/test_corpus_retrieval.py) rather than real
PDF files, since corpus/raw/ is gitignored and must not be a CI dependency
-- but the text still goes through the real extraction -> provenance-bridge
-> retrieval -> deterministic-safety-layer chain, not a mock of any of it.
"""

from datetime import date, datetime, timezone

from agents.agent_a_retrieval.corpus_retrieval import CorpusRetriever
from agents.agent_c_environment.monitor import EnvironmentalMonitor
from agents.protocols.schemas import SafetyState
from api.models import SensorReading
from extraction.models import SDSMetadata
from extraction.pipeline import extract_document
from safety.state_machine import DeterministicSafetyEvaluator


def _document(chemical_name: str, storage_line: str):
    metadata = SDSMetadata(
        document_id=f"doc_{chemical_name}",
        chemical_name=chemical_name,
        supplier="Test Supplier",
        retrieval_date=date.today(),
    )
    raw_text = f"SECTION 7: Handling and storage\n{storage_line}\n"
    return extract_document(raw_text, metadata)


def _reading(zone_id: str, temperature_celsius: float) -> SensorReading:
    return SensorReading(
        zone_id=zone_id,
        temperature_celsius=temperature_celsius,
        humidity_percent=45.0,
        timestamp=datetime.now(timezone.utc),
        device_id="esp32-test",
    )


def _monitor(zone_inventory: dict) -> EnvironmentalMonitor:
    documents = [
        _document(
            "Hydrogen peroxide solution",
            "Recommended storage temperature : 2 - 8 \xb0C",
        ),
        # Real corpus fact (Layer 3 benchmark): most SDS in this corpus have
        # no storage-temperature field at all -- represented here honestly,
        # not papered over with an invented threshold.
        _document("Ethanol", "Keep container tightly closed."),
    ]
    retriever = CorpusRetriever(documents)
    evaluator = DeterministicSafetyEvaluator()
    return EnvironmentalMonitor(retriever, evaluator, zone_inventory)


def test_reading_within_range_is_safe() -> None:
    monitor = _monitor({"Zone_C": ["Hydrogen peroxide solution"]})
    evaluation = monitor.handle_reading(_reading("Zone_C", 5.0))

    assert evaluation.aggregated_state == SafetyState.SAFE
    assert evaluation.is_excursion is False
    assert all(c.state == SafetyState.SAFE for c in evaluation.checks)


def test_reading_above_max_threshold_is_warning() -> None:
    monitor = _monitor({"Zone_C": ["Hydrogen peroxide solution"]})
    evaluation = monitor.handle_reading(_reading("Zone_C", 12.0))

    assert evaluation.aggregated_state == SafetyState.WARNING
    assert evaluation.is_excursion is True
    max_check = next(
        c for c in evaluation.checks if c.metric_name == "max_storage_temperature"
    )
    assert max_check.state == SafetyState.WARNING
    assert max_check.threshold_value == 8.0


def test_reading_below_min_threshold_is_warning() -> None:
    monitor = _monitor({"Zone_C": ["Hydrogen peroxide solution"]})
    evaluation = monitor.handle_reading(_reading("Zone_C", -1.0))

    assert evaluation.aggregated_state == SafetyState.WARNING
    assert evaluation.is_excursion is True
    min_check = next(
        c for c in evaluation.checks if c.metric_name == "min_storage_temperature"
    )
    assert min_check.state == SafetyState.WARNING
    assert min_check.threshold_value == 2.0


def test_chemical_with_no_extracted_threshold_is_unknown_not_safe() -> None:
    """The central principle in miniature: absence of evidence must never
    collapse to a SAFE verdict, even when nothing looks obviously wrong."""
    monitor = _monitor({"Zone_A": ["Ethanol"]})
    evaluation = monitor.handle_reading(_reading("Zone_A", 20.0))

    assert evaluation.aggregated_state == SafetyState.UNKNOWN
    assert evaluation.is_excursion is False
    assert all(c.state == SafetyState.UNKNOWN for c in evaluation.checks)


def test_worst_case_aggregation_across_chemicals_in_one_zone() -> None:
    """One WARNING chemical must dominate the zone's display state even
    alongside SAFE and UNKNOWN chemicals in the same reading."""
    monitor = _monitor({"Zone_Mixed": ["Hydrogen peroxide solution", "Ethanol"]})
    evaluation = monitor.handle_reading(_reading("Zone_Mixed", 12.0))

    assert evaluation.aggregated_state == SafetyState.WARNING
    assert evaluation.is_excursion is True
    states = {c.chemical_name: c.state for c in evaluation.checks}
    assert states["Ethanol"] == SafetyState.UNKNOWN


def test_unrecognised_zone_is_unknown_not_safe() -> None:
    monitor = _monitor({"Zone_C": ["Hydrogen peroxide solution"]})
    evaluation = monitor.handle_reading(_reading("Zone_Nonexistent", 20.0))

    assert evaluation.checks == []
    assert evaluation.aggregated_state == SafetyState.UNKNOWN
    assert evaluation.is_excursion is False


def test_previous_state_is_tracked_across_readings_for_same_zone() -> None:
    monitor = _monitor({"Zone_C": ["Hydrogen peroxide solution"]})

    first = monitor.handle_reading(_reading("Zone_C", 5.0))
    assert first.previous_state is None

    second = monitor.handle_reading(_reading("Zone_C", 12.0))
    assert second.previous_state == SafetyState.SAFE
    assert second.aggregated_state == SafetyState.WARNING
