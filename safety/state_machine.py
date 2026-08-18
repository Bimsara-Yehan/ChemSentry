"""Deterministic SAFE/WARNING/UNKNOWN safety evaluation state machine (M3).

Central Principle:
No safety threshold is ever hardcoded. Every threshold is retrieved from a versioned
source document at query time and cited back to the user. No LLM ever participates
in deciding the safety state.
"""

from typing import List, Optional
from agents.protocols.schemas import (
    ProvenancedThreshold,
    SafetyEvaluationRequest,
    SafetyEvaluationResult,
    SafetyState,
)
from safety.provenance import build_citation_string


class DeterministicSafetyEvaluator:
    """Evaluates telemetry readings against retrieved SDS thresholds deterministically."""

    def __init__(self, conflict_tolerance_pct: float = 5.0) -> None:
        """Initialize evaluator with acceptable percentage tolerance for supplier variance."""
        self.conflict_tolerance_pct = conflict_tolerance_pct

    def evaluate(
        self,
        request: SafetyEvaluationRequest,
        thresholds: List[ProvenancedThreshold],
    ) -> SafetyEvaluationResult:
        """Evaluate a single sensor reading against retrieved SDS thresholds.
        
        Returns:
            SafetyEvaluationResult with state SAFE, WARNING, or UNKNOWN,
            accompanied by reasoning and source citation provenance.
        """
        # 1. No thresholds retrieved -> UNKNOWN
        if not thresholds:
            return SafetyEvaluationResult(
                state=SafetyState.UNKNOWN,
                chemical_name=request.chemical_name,
                zone_id=request.zone_id,
                metric_name=request.metric_name,
                current_value=request.current_value,
                unit=request.unit,
                provenance=None,
                reasoning=(
                    f"UNKNOWN: No versioned SDS threshold retrieved for metric '{request.metric_name}' "
                    f"on chemical '{request.chemical_name}' in zone '{request.zone_id}'."
                ),
            )

        # Filter thresholds matching requested metric
        matching_thresholds = [t for t in thresholds if t.metric_name == request.metric_name]
        if not matching_thresholds:
            return SafetyEvaluationResult(
                state=SafetyState.UNKNOWN,
                chemical_name=request.chemical_name,
                zone_id=request.zone_id,
                metric_name=request.metric_name,
                current_value=request.current_value,
                unit=request.unit,
                provenance=None,
                reasoning=(
                    f"UNKNOWN: Retrieved SDS documents contain no threshold data matching "
                    f"requested metric '{request.metric_name}'."
                ),
            )

        # 2. Check for supplier authority and conflicts
        reconciled_threshold, conflict_reason = self._reconcile_thresholds(matching_thresholds)
        if conflict_reason:
            return SafetyEvaluationResult(
                state=SafetyState.UNKNOWN,
                chemical_name=request.chemical_name,
                zone_id=request.zone_id,
                metric_name=request.metric_name,
                current_value=request.current_value,
                unit=request.unit,
                provenance=None,
                reasoning=f"UNKNOWN: {conflict_reason}",
            )

        # 3. Deterministic state evaluation against reconciled threshold
        target_threshold = reconciled_threshold.value
        is_exceeded = request.current_value >= target_threshold

        if is_exceeded:
            state = SafetyState.WARNING
            reasoning = (
                f"WARNING: Current {request.metric_name} ({request.current_value} {request.unit}) "
                f"meets or exceeds retrieved SDS safety threshold ({target_threshold} {reconciled_threshold.unit}). "
                f"Source: {reconciled_threshold.citation}"
            )
        else:
            state = SafetyState.SAFE
            reasoning = (
                f"SAFE: Current {request.metric_name} ({request.current_value} {request.unit}) "
                f"is strictly below retrieved SDS safety threshold ({target_threshold} {reconciled_threshold.unit}). "
                f"Source: {reconciled_threshold.citation}"
            )

        return SafetyEvaluationResult(
            state=state,
            chemical_name=request.chemical_name,
            zone_id=request.zone_id,
            metric_name=request.metric_name,
            current_value=request.current_value,
            threshold_value=target_threshold,
            unit=request.unit,
            provenance=reconciled_threshold,
            reasoning=reasoning,
        )

    def _reconcile_thresholds(
        self, thresholds: List[ProvenancedThreshold]
    ) -> tuple[Optional[ProvenancedThreshold], Optional[str]]:
        """Select highest authority threshold or flag unresolvable supplier conflicts."""
        if len(thresholds) == 1:
            return thresholds[0], None

        # Sort by authority score descending
        sorted_thresholds = sorted(thresholds, key=lambda t: t.authority_score, reverse=True)
        top_threshold = sorted_thresholds[0]
        second_threshold = sorted_thresholds[1]

        # If top authority is strictly higher than second, use top
        if top_threshold.authority_score > second_threshold.authority_score:
            return top_threshold, None

        # Equal top authority scores: check variance threshold
        if top_threshold.value != 0:
            variance_pct = abs(top_threshold.value - second_threshold.value) / abs(top_threshold.value) * 100.0
        else:
            variance_pct = abs(top_threshold.value - second_threshold.value) * 100.0

        if variance_pct > self.conflict_tolerance_pct:
            conflict_msg = (
                f"Conflicting thresholds detected across equal-authority suppliers "
                f"({top_threshold.supplier_name}: {top_threshold.value} {top_threshold.unit} vs "
                f"{second_threshold.supplier_name}: {second_threshold.value} {second_threshold.unit}, "
                f"variance: {variance_pct:.1f}%)."
            )
            return None, conflict_msg

        return top_threshold, None
