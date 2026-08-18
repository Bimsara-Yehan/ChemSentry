"""Provenance model and citation generator for SDS-sourced safety thresholds (M2/M3)."""

from typing import Dict, List, Optional
from agents.protocols.schemas import ProvenancedThreshold


# Default supplier authority hierarchy mapping
DEFAULT_AUTHORITY_SCORES: Dict[str, float] = {
    "Primary Manufacturer": 1.0,
    "Authorized Distributor": 0.85,
    "Generic Safety Registry": 0.70,
    "Unverified Third-Party": 0.50,
}


def build_citation_string(
    chemical_name: str,
    sds_id: str,
    supplier_name: str,
    section_number: str,
    metric_name: str,
    value: float,
    unit: str,
) -> str:
    """Build a standardized, audit-ready human readable citation string.
    
    Example:
        "[SDS-ACETONE-2026-v2] Section 7 (Handling and Storage) - Sigma-Aldrich:
         max_storage_temperature threshold = 25.0 C"
    """
    return (
        f"[{sds_id}] {section_number} - {supplier_name}: "
        f"{metric_name} threshold = {value} {unit}"
    )


def resolve_supplier_authority(supplier_name: str, custom_score: Optional[float] = None) -> float:
    """Resolve authority score for a given SDS supplier."""
    if custom_score is not None:
        return max(0.0, min(1.0, custom_score))
    return DEFAULT_AUTHORITY_SCORES.get(supplier_name, 0.75)
