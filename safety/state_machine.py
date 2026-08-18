"""Deterministic SAFE/WARNING/UNKNOWN safety evaluation state machine (M3).

Central Principle:
No safety threshold is ever hardcoded. Every threshold is retrieved from a versioned
source document at query time and cited back to the user. No LLM ever participates
in deciding the safety state.
"""

from typing import List, Optional

from agents.agent_b_analysis.reconciler import (
    DEFAULT_CONFLICT_TOLERANCE_PCT,
    EvidenceReconciler,
)
from agents.protocols.schemas import (
    ProvenancedThreshold,
    SafetyEvaluationRequest,
    SafetyEvaluationResult,
    SafetyState,
    ThresholdDirection,
)

# NOTE: reconciliation-policy default, not a per-chemical safety threshold -- see
# agents/agent_b_analysis/reconciler.py for why this is a tracked gap rather than a
# fully versioned/cited value.
DEFAULT_HAZARD_JACCARD_THRESHOLD = 0.6


class DeterministicSafetyEvaluator:
    """Evaluates telemetry readings against retrieved SDS thresholds deterministically.

    Delegates authority-hierarchy and hazard-conflict reconciliation to the shared
    EvidenceReconciler (agents/agent_b_analysis/reconciler.py) rather than
    reimplementing it, so the two pipeline stages described in the architecture
    (Evidence Reconciler -> Deterministic Safety Layer) can't silently diverge.
    """

    def __init__(
        self,
        conflict_tolerance_pct: float = DEFAULT_CONFLICT_TOLERANCE_PCT,
        hazard_jaccard_threshold: float = DEFAULT_HAZARD_JACCARD_THRESHOLD,
    ) -> None:
        """Initialize evaluator with acceptable percentage tolerance for supplier variance."""
        self.conflict_tolerance_pct = conflict_tolerance_pct
        self.hazard_jaccard_threshold = hazard_jaccard_threshold
        self._reconciler = EvidenceReconciler()

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
            return self._unknown_result(
                request,
                f"No versioned SDS threshold retrieved for metric '{request.metric_name}' "
                f"on chemical '{request.chemical_name}' in zone '{request.zone_id}'.",
            )

        # Filter thresholds matching requested metric
        matching_thresholds = [
            t for t in thresholds if t.metric_name == request.metric_name
        ]
        if not matching_thresholds:
            return self._unknown_result(
                request,
                f"Retrieved SDS documents contain no threshold data matching "
                f"requested metric '{request.metric_name}'.",
            )

        # 2. Hazard-statement conflicts across sources take precedence over numeric
        # reconciliation -- two sources that disagree on hazard classification are
        # unresolvable evidence even if their numeric thresholds happen to agree.
        hazard_conflict = self._detect_hazard_conflicts(matching_thresholds)
        if hazard_conflict:
            return self._unknown_result(request, hazard_conflict)

        # 3. Check for supplier authority and numeric conflicts
        reconciled_threshold, conflict_reason = self._reconcile_thresholds(
            matching_thresholds
        )
        if conflict_reason:
            return self._unknown_result(request, conflict_reason)

        # 4. A threshold in a different unit than the reading cannot be compared
        # without a conversion this system has no versioned source for -- UNKNOWN
        # rather than silently assuming compatible units.
        if reconciled_threshold.unit.strip().lower() != request.unit.strip().lower():
            return self._unknown_result(
                request,
                f"Retrieved threshold is in '{reconciled_threshold.unit}' but the reading is in "
                f"'{request.unit}'; cannot compare without a sourced unit conversion. "
                f"Source: {reconciled_threshold.citation}",
            )

        # 5. Deterministic state evaluation against reconciled threshold, respecting
        # whether the threshold is a ceiling (max) or a floor (min).
        target_threshold = reconciled_threshold.value
        if reconciled_threshold.direction == ThresholdDirection.MAX:
            is_unsafe = request.current_value >= target_threshold
            unsafe_phrase, safe_phrase = "meets or exceeds", "is strictly below"
        else:
            is_unsafe = request.current_value <= target_threshold
            unsafe_phrase, safe_phrase = "is at or below", "is strictly above"

        if is_unsafe:
            state = SafetyState.WARNING
            reasoning = (
                f"WARNING: Current {request.metric_name} ({request.current_value} {request.unit}) "
                f"{unsafe_phrase} retrieved SDS safety threshold ({target_threshold} {reconciled_threshold.unit}). "
                f"Source: {reconciled_threshold.citation}"
            )
        else:
            state = SafetyState.SAFE
            reasoning = (
                f"SAFE: Current {request.metric_name} ({request.current_value} {request.unit}) "
                f"{safe_phrase} retrieved SDS safety threshold ({target_threshold} {reconciled_threshold.unit}). "
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

    def _unknown_result(
        self, request: SafetyEvaluationRequest, reason: str
    ) -> SafetyEvaluationResult:
        """Build the UNKNOWN-state result shared by every early-exit path in evaluate()."""
        return SafetyEvaluationResult(
            state=SafetyState.UNKNOWN,
            chemical_name=request.chemical_name,
            zone_id=request.zone_id,
            metric_name=request.metric_name,
            current_value=request.current_value,
            unit=request.unit,
            provenance=None,
            reasoning=f"UNKNOWN: {reason}",
        )

    def _detect_hazard_conflicts(
        self, thresholds: List[ProvenancedThreshold]
    ) -> Optional[str]:
        """Pairwise-check hazard statement sets across sources that provided any."""
        sources = [t for t in thresholds if t.hazard_statements]
        for i in range(len(sources)):
            for j in range(i + 1, len(sources)):
                a, b = sources[i], sources[j]
                has_conflict, _sim_score, explanation = (
                    self._reconciler.detect_hazard_conflicts(
                        a.hazard_statements,
                        b.hazard_statements,
                        self.hazard_jaccard_threshold,
                    )
                )
                if has_conflict:
                    return (
                        f"Hazard statement conflict between '{a.supplier_name}' and "
                        f"'{b.supplier_name}' ({explanation})"
                    )
        return None

    def _reconcile_thresholds(
        self, thresholds: List[ProvenancedThreshold]
    ) -> tuple[Optional[ProvenancedThreshold], Optional[str]]:
        """Select highest authority threshold or flag unresolvable supplier conflicts."""
        if len(thresholds) == 1:
            return thresholds[0], None

        primary, notes = self._reconciler.select_authoritative_threshold(
            thresholds, self.conflict_tolerance_pct
        )
        if primary is None:
            return None, notes[-1]
        return primary, None
