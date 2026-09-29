"""Evidence Reconciler -- version comparison, Jaccard conflict detection, authority hierarchy (M3)."""

from agents.protocols.schemas import ProvenancedThreshold
from safety.reconciliation_policy import (
    CONFLICT_TOLERANCE_PCT,
    get_conflict_tolerance_pct,
    get_hazard_jaccard_threshold,
)

# Backward-compatible alias (callers that still reference DEFAULT_CONFLICT_TOLERANCE_PCT
# continue to work; see safety/reconciliation_policy.py for the authoritative value,
# rationale, and version).
DEFAULT_CONFLICT_TOLERANCE_PCT: float = CONFLICT_TOLERANCE_PCT


class EvidenceReconciler:
    """Reconciles conflicting Safety Data Sheet (SDS) evidence across suppliers and document versions."""

    @staticmethod
    def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
        """Calculate Jaccard similarity coefficient between two token/hazard sets.

        Problem this solves:
            Quantifies overlap between GHS hazard statements across suppliers to
            detect contradictory classifications without assuming exact set equality.

        Why this technique:
            Jaccard coefficient |A ∩ B| / |A ∪ B| is invariant to set size asymmetry
            and provides a bounded [0, 1] metric directly tunable via policy.

        Formula: J(A, B) = |A ∩ B| / |A ∪ B|
        """
        if not set_a and not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)

    def detect_hazard_conflicts(
        self,
        hazards_doc_a: set[str],
        hazards_doc_b: set[str],
        min_jaccard_threshold: float | None = None,
    ) -> tuple[bool, float, str]:
        """Detect conflict between hazard statement sets from two supplier SDS documents.

        Problem this solves:
            Flags unresolvable discrepancies in GHS hazard classifications across suppliers
            before numerical threshold evaluation occurs.

        Why this technique:
            Compares Jaccard similarity against the versioned policy threshold
            retrieved from safety/reconciliation_policy.json, forcing UNKNOWN when
            suppliers disagree on fundamental chemical hazards.

        Returns:
            Tuple of (has_conflict: bool, similarity_score: float, explanation: str)
        """
        threshold = (
            min_jaccard_threshold
            if min_jaccard_threshold is not None
            else get_hazard_jaccard_threshold()
        )
        if not hazards_doc_a and not hazards_doc_b:
            return (
                True,
                0.0,
                "No hazard statements extracted from either source; cannot confirm agreement.",
            )

        sim_score = self.jaccard_similarity(hazards_doc_a, hazards_doc_b)
        has_conflict = sim_score < threshold

        if has_conflict:
            explanation = (
                f"Hazard statements conflict between supplier sources "
                f"(Jaccard similarity = {sim_score:.2f} < threshold {threshold:.2f})."
            )
        else:
            explanation = (
                f"Hazard statements align (Jaccard similarity = {sim_score:.2f})."
            )

        return has_conflict, sim_score, explanation

    def select_authoritative_threshold(
        self,
        thresholds: list[ProvenancedThreshold],
        conflict_tolerance_pct: float | None = None,
    ) -> tuple[ProvenancedThreshold | None, list[str]]:
        """Select the single most authoritative threshold from a list of retrieved supplier thresholds.

        Problem this solves:
            Resolves multiple candidate thresholds from different suppliers using
            a tiered authority hierarchy, while preventing silent selection when equal-authority
            sources disagree beyond acceptable tolerance.

        Why this technique:
            Sorts by authority score and calculates relative percentage variance across
            all top-tier candidates against the versioned policy tolerance from
            safety/reconciliation_policy.json.

        If more than one source shares the top authority score, all of them (not just
        the first two) are checked for value variance beyond `conflict_tolerance_pct`;
        an unresolvable conflict returns (None, audit_notes) instead of guessing.
        """
        tolerance = (
            conflict_tolerance_pct
            if conflict_tolerance_pct is not None
            else get_conflict_tolerance_pct()
        )
        if not thresholds:
            raise ValueError("Cannot reconcile empty list of thresholds")

        sorted_thresholds = sorted(
            thresholds, key=lambda t: t.authority_score, reverse=True
        )
        max_authority = sorted_thresholds[0].authority_score
        top_group = [t for t in sorted_thresholds if t.authority_score == max_authority]

        if len(top_group) > 1:
            values = [t.value for t in top_group]
            value_range = max(values) - min(values)
            reference = max(abs(v) for v in values)
            variance_pct = (value_range / reference * 100.0) if reference > 0 else 0.0

            if variance_pct > tolerance:
                names = ", ".join(
                    f"{t.supplier_name}={t.value}{t.unit}" for t in top_group
                )
                return None, [
                    (
                        f"Conflict: {len(top_group)} equal-authority sources (score={max_authority}) diverge "
                        f"beyond {tolerance:.1f}% tolerance ({names}; variance={variance_pct:.1f}%)."
                    )
                ]

        primary = top_group[0]
        audit_notes = [
            f"Selected primary authority '{primary.supplier_name}' (score={primary.authority_score})"
        ]

        for secondary in sorted_thresholds:
            if secondary is primary:
                continue
            audit_notes.append(
                f"Superseded secondary source '{secondary.supplier_name}' (score={secondary.authority_score})"
            )

        return primary, audit_notes
