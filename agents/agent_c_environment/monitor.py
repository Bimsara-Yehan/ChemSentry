"""Agent C -- environmental monitor, the forced hand-off to Agent A (M4).

Plan Part V §12, the constraint that makes this a genuine multi-agent
system rather than one program with three modules: Agent C *knows* a zone's
sensor reading and *knows which chemicals are physically stored there* (a
simple, database-backed inventory -- plan §16 is explicit that "container
tracking is not our research contribution"), but it holds no safety
threshold whatsoever. For every reading, it must ask Agent A
(`agents.agent_a_retrieval.corpus_retrieval.CorpusRetriever`) what the
retrieved evidence says, and only the deterministic safety layer
(`safety.state_machine.DeterministicSafetyEvaluator`) decides SAFE/WARNING/
UNKNOWN. If Agent C hardcoded even one threshold to skip that hand-off, it
would directly violate the project's central principle.

`EnvironmentalMonitor` is deliberately MQTT- and database-free at this
layer -- it takes an already-parsed `SensorReading` and an injected zone
inventory mapping, the same dependency-injection shape
`agents.agent_a_retrieval.corpus_retrieval.CorpusRetriever` uses (a
constructor that takes plain data, plus a separate convenience path for the
real I/O). That's what makes it fully unit-testable against the real
`CorpusRetriever` + `DeterministicSafetyEvaluator` without a live broker or
database -- see `mqtt_subscriber.py` and `zone_inventory.py` for the thin
real-I/O wrappers around this class.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agents.agent_a_retrieval.corpus_retrieval import CorpusRetriever
from agents.protocols.schemas import (
    ProvenancedThreshold,
    SafetyEvaluationRequest,
    SafetyState,
)
from api.models import SensorReading
from safety.state_machine import DeterministicSafetyEvaluator

# Only metrics with at least one real extracted value anywhere in this
# corpus are checked. Storage humidity has zero real occurrences across
# every document (confirmed while building evaluation Layer 3) -- checking
# it anyway would mean every single reading comes back UNKNOWN for that
# metric on every chemical, permanently masking whatever the temperature
# checks find. Documented here rather than silently degrading every zone's
# state; extend this list once a real humidity threshold exists to extract.
_MONITORED_METRICS = ("max_storage_temperature", "min_storage_temperature")


@dataclass
class ChemicalCheck:
    """One (chemical, metric) safety evaluation for a single reading."""

    chemical_name: str
    metric_name: str
    state: SafetyState
    current_value: float
    threshold_value: float | None
    reasoning: str
    provenance: ProvenancedThreshold | None


@dataclass
class ZoneEvaluation:
    """Result of handling one sensor reading for a zone."""

    zone_id: str
    reading: SensorReading
    checks: list[ChemicalCheck] = field(default_factory=list)
    aggregated_state: SafetyState = SafetyState.UNKNOWN
    is_excursion: bool = False
    previous_state: SafetyState | None = None


class EnvironmentalMonitor:
    """Agent C: tracks zone state, holds no chemical knowledge of its own.

    Example:
        >>> monitor = EnvironmentalMonitor(retriever, evaluator, zone_inventory)
        >>> evaluation = monitor.handle_reading(reading)
        >>> evaluation.is_excursion  # True only if a real WARNING was found
    """

    def __init__(
        self,
        retriever: CorpusRetriever,
        evaluator: DeterministicSafetyEvaluator,
        zone_inventory: dict[str, list[str]],
    ) -> None:
        """
        Args:
            retriever: Real Agent A retrieval entry point -- resolves each
                inventory chemical's name (tolerant to typos) and returns
                cited thresholds. Agent C never touches chemical data
                directly; every lookup goes through this.
            evaluator: The deterministic safety layer. Never an LLM, per the
                project's central principle.
            zone_inventory: zone_id -> list of chemical names physically
                stored there. A simulated, database-backed mapping (plan
                §16) -- see zone_inventory.py for the real DB-backed loader;
                this constructor takes a plain dict so the class itself has
                no database dependency.
        """
        self._retriever = retriever
        self._evaluator = evaluator
        self._zone_inventory = zone_inventory
        self._last_state: dict[str, SafetyState] = {}

    def handle_reading(self, reading: SensorReading) -> ZoneEvaluation:
        """Evaluate one sensor reading against every chemical in its zone.

        Args:
            reading: A single parsed DHT22-shaped reading (temperature +
                humidity) for one zone.

        Returns:
            ZoneEvaluation with one ChemicalCheck per (chemical, monitored
            metric) in the zone's inventory, an aggregated display state,
            and `is_excursion` -- True only when at least one check is a
            genuine WARNING (not merely UNKNOWN; see module docstring on
            _MONITORED_METRICS for why UNKNOWN must not by itself count as
            an excursion here).
        """
        chemicals = self._zone_inventory.get(reading.zone_id, [])
        checks: list[ChemicalCheck] = []

        for chemical_name in chemicals:
            thresholds = self._retriever.get_thresholds(chemical_name)
            for metric_name in _MONITORED_METRICS:
                request = SafetyEvaluationRequest(
                    chemical_name=chemical_name,
                    zone_id=reading.zone_id,
                    metric_name=metric_name,
                    current_value=reading.temperature_celsius,
                    unit="C",
                )
                matching = [t for t in thresholds if t.metric_name == metric_name]
                result = self._evaluator.evaluate(request, matching)
                checks.append(
                    ChemicalCheck(
                        chemical_name=chemical_name,
                        metric_name=metric_name,
                        state=result.state,
                        current_value=reading.temperature_celsius,
                        threshold_value=result.threshold_value,
                        reasoning=result.reasoning,
                        provenance=result.provenance,
                    )
                )

        aggregated = self._aggregate(checks)
        previous = self._last_state.get(reading.zone_id)
        self._last_state[reading.zone_id] = aggregated

        return ZoneEvaluation(
            zone_id=reading.zone_id,
            reading=reading,
            checks=checks,
            aggregated_state=aggregated,
            is_excursion=any(c.state == SafetyState.WARNING for c in checks),
            previous_state=previous,
        )

    @staticmethod
    def _aggregate(checks: list[ChemicalCheck]) -> SafetyState:
        """Zone-level display state: worst case wins (WARNING > UNKNOWN > SAFE).

        An empty zone (nothing in inventory, or an unrecognised zone_id) is
        reported UNKNOWN, not SAFE -- there is no evidence a truly empty
        zone is safe, only that nothing was checked.
        """
        if not checks:
            return SafetyState.UNKNOWN
        states = {c.state for c in checks}
        if SafetyState.WARNING in states:
            return SafetyState.WARNING
        if SafetyState.UNKNOWN in states:
            return SafetyState.UNKNOWN
        return SafetyState.SAFE
