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
    ThresholdDirection,
)
from safety.reconciliation_policy import (
    CONFLICT_TOLERANCE_PCT,
    HAZARD_JACCARD_THRESHOLD,
    get_conflict_tolerance_pct,
    get_hazard_jaccard_threshold,
    get_policy_version,
)

# Backward-compatible aliases; see safety/reconciliation_policy.py for the
# authoritative value, rationale, and governance changelog.
DEFAULT_CONFLICT_TOLERANCE_PCT: float = CONFLICT_TOLERANCE_PCT
DEFAULT_HAZARD_JACCARD_THRESHOLD: float = HAZARD_JACCARD_THRESHOLD


class DeterministicSafetyEvaluator:
    """Evaluates telemetry readings against retrieved SDS thresholds deterministically.

    Delegates authority-hierarchy and hazard-conflict reconciliation to the shared
    EvidenceReconciler (agents/agent_b_analysis/reconciler.py) rather than
    reimplementing it, so the two pipeline stages described in the architecture
    (Evidence Reconciler -> Deterministic Safety Layer) can't silently diverge.
    """

    def __init__(
        self,
        conflict_tolerance_pct: Optional[float] = None,
        hazard_jaccard_threshold: Optional[float] = None,
        policy_version: Optional[str] = None,
    ) -> None:
        """Initialize evaluator with versioned policy parameters.

        Problem this solves:
            Configures the deterministic evaluator with governance thresholds and
            provenance versioning loaded from the active reconciliation policy.

        Why this technique:
            Defaulting to policy getters ensures no hardcoded numbers are baked
            into code while permitting parameter injection for test isolation.
        """
        from agents.agent_b_analysis.reconciler import EvidenceReconciler

        self.conflict_tolerance_pct = (
            conflict_tolerance_pct
            if conflict_tolerance_pct is not None
            else get_conflict_tolerance_pct()
        )
        self.hazard_jaccard_threshold = (
            hazard_jaccard_threshold
            if hazard_jaccard_threshold is not None
            else get_hazard_jaccard_threshold()
        )
        self.policy_version = (
            policy_version if policy_version is not None else get_policy_version()
        )
        self._reconciler = EvidenceReconciler()

    def evaluate(
        self,
        request: SafetyEvaluationRequest,
        thresholds: List[ProvenancedThreshold],
    ) -> SafetyEvaluationResult:
        """Evaluate a single sensor reading against retrieved SDS thresholds.

        Problem this solves:
            Provides a deterministic, verifiable safety verdict (SAFE / WARNING / UNKNOWN)
            without LLM non-determinism, backed by explicit citations and policy provenance.

        Why this technique:
            Executes a multi-stage deterministic state machine (empty check -> hazard
            conflict -> supplier reconciliation -> unit validation -> directional threshold
            comparison) ensuring zero hallucinations on the safety-critical path.

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
                f"Source: {reconciled_threshold.citation} [policy_version={self.policy_version}]"
            )
        else:
            state = SafetyState.SAFE
            reasoning = (
                f"SAFE: Current {request.metric_name} ({request.current_value} {request.unit}) "
                f"{safe_phrase} retrieved SDS safety threshold ({target_threshold} {reconciled_threshold.unit}). "
                f"Source: {reconciled_threshold.citation} [policy_version={self.policy_version}]"
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
        """Build the UNKNOWN-state result shared by every early-exit path in evaluate().

        Problem this solves:
            Standardizes UNKNOWN result construction with consistent audit metadata
            and policy version tags across all evaluation guardrails.

        Why this technique:
            Central helper prevents duplicate object construction and guarantees
            policy version is threaded into every early-exit explanation.
        """
        return SafetyEvaluationResult(
            state=SafetyState.UNKNOWN,
            chemical_name=request.chemical_name,
            zone_id=request.zone_id,
            metric_name=request.metric_name,
            current_value=request.current_value,
            unit=request.unit,
            provenance=None,
            reasoning=f"UNKNOWN: {reason} [policy_version={self.policy_version}]",
        )

    def _detect_hazard_conflicts(
        self, thresholds: List[ProvenancedThreshold]
    ) -> Optional[str]:
        """Pairwise-check hazard statement sets across sources that provided any.

        Problem this solves:
            Identifies conflicting hazard classifications across all supplied SDS documents.

        Why this technique:
            Performs exhaustive pairwise Jaccard comparison using the configured
            policy threshold to catch any cross-supplier hazard contradictions.
        """
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
        """Select highest authority threshold or flag unresolvable supplier conflicts.

        Problem this solves:
            Extracts the authoritative threshold or detects unresolvable variance among
            top-tier sources.

        Why this technique:
            Delegates to EvidenceReconciler to maintain a single source of truth for
            authority ranking and percentage variance calculations.
        """
        if len(thresholds) == 1:
            return thresholds[0], None

        primary, notes = self._reconciler.select_authoritative_threshold(
            thresholds, self.conflict_tolerance_pct
        )
        if primary is None:
            return None, notes[-1]
        return primary, None
