"""Evidence Reconciler -- version comparison, Jaccard conflict detection, authority hierarchy (M3)."""

from typing import Any, Dict, List, Set, Tuple
from agents.protocols.schemas import ProvenancedThreshold


class EvidenceReconciler:
    """Reconciles conflicting Safety Data Sheet (SDS) evidence across suppliers and document versions."""

    @staticmethod
    def jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
        """Calculate Jaccard similarity coefficient between two token/hazard sets.
        
        Formula: J(A, B) = |A ∩ B| / |A ∪ B|
        """
        if not set_a and not set_b:
            return 1.0
        intersection = set_a.intersection(set_b)
        union = set_a.union(set_b)
        return len(intersection) / len(union) if union else 0.0

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
        sim_score = self.jaccard_similarity(hazards_doc_a, hazards_doc_b)
        has_conflict = sim_score < min_jaccard_threshold

        if has_conflict:
            explanation = (
                f"Hazard statements conflict between supplier sources "
                f"(Jaccard similarity = {sim_score:.2f} < threshold {min_jaccard_threshold:.2f})."
            )
        else:
            explanation = f"Hazard statements align (Jaccard similarity = {sim_score:.2f})."

        return has_conflict, sim_score, explanation

    def select_authoritative_threshold(
        self, thresholds: List[ProvenancedThreshold]
    ) -> Tuple[ProvenancedThreshold, List[str]]:
        """Select single most authoritative threshold from a list of retrieved supplier thresholds."""
        if not thresholds:
            raise ValueError("Cannot reconcile empty list of thresholds")

        # Sort by authority_score descending
        sorted_thresholds = sorted(thresholds, key=lambda t: t.authority_score, reverse=True)
        primary = sorted_thresholds[0]
        audit_notes = [f"Selected primary authority '{primary.supplier_name}' (score={primary.authority_score})"]

        for secondary in sorted_thresholds[1:]:
            audit_notes.append(
                f"Superseded secondary source '{secondary.supplier_name}' (score={secondary.authority_score})"
            )

        return primary, audit_notes
