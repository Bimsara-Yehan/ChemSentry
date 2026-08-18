"""Evidence Reconciler -- version comparison, Jaccard conflict detection, authority hierarchy (M3)."""

from typing import List, Optional, Set, Tuple

from agents.protocols.schemas import ProvenancedThreshold

# NOTE: reconciliation-policy default, not a per-chemical safety threshold -- this
# gates how much numeric variance across equal-authority sources is tolerated before
# forcing UNKNOWN. Tracked as a known gap: should ultimately be sourced from a
# versioned governance document like every other safety-relevant number, once a
# config-retrieval subsystem exists for it.
DEFAULT_CONFLICT_TOLERANCE_PCT = 5.0


class EvidenceReconciler:
    """Reconciles conflicting Safety Data Sheet (SDS) evidence across suppliers and document versions."""

    @staticmethod
    def jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
        """Calculate Jaccard similarity coefficient between two token/hazard sets.

        Formula: J(A, B) = |A ∩ B| / |A ∪ B|
        """
        if not set_a and not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)

    def detect_hazard_conflicts(
        self,
        hazards_doc_a: Set[str],
        hazards_doc_b: Set[str],
        min_jaccard_threshold: float = 0.6,
    ) -> Tuple[bool, float, str]:
        """Detect conflict between hazard statement sets from two supplier SDS documents.

        Returns:
            Tuple of (has_conflict: bool, similarity_score: float, explanation: str)
        """
        if not hazards_doc_a and not hazards_doc_b:
            return (
                True,
                0.0,
                "No hazard statements extracted from either source; cannot confirm agreement.",
            )

        sim_score = self.jaccard_similarity(hazards_doc_a, hazards_doc_b)
        has_conflict = sim_score < min_jaccard_threshold

        if has_conflict:
            explanation = (
                f"Hazard statements conflict between supplier sources "
                f"(Jaccard similarity = {sim_score:.2f} < threshold {min_jaccard_threshold:.2f})."
            )
        else:
            explanation = (
                f"Hazard statements align (Jaccard similarity = {sim_score:.2f})."
            )

        return has_conflict, sim_score, explanation

    def select_authoritative_threshold(
        self,
        thresholds: List[ProvenancedThreshold],
        conflict_tolerance_pct: float = DEFAULT_CONFLICT_TOLERANCE_PCT,
    ) -> Tuple[Optional[ProvenancedThreshold], List[str]]:
        """Select the single most authoritative threshold from a list of retrieved supplier thresholds.

        If more than one source shares the top authority score, all of them (not just
        the first two) are checked for value variance beyond `conflict_tolerance_pct`;
        an unresolvable conflict returns (None, audit_notes) instead of guessing.
        """
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

            if variance_pct > conflict_tolerance_pct:
                names = ", ".join(
                    f"{t.supplier_name}={t.value}{t.unit}" for t in top_group
                )
                return None, [
                    f"Conflict: {len(top_group)} equal-authority sources (score={max_authority}) diverge "
                    f"beyond {conflict_tolerance_pct:.1f}% tolerance ({names}; variance={variance_pct:.1f}%)."
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
