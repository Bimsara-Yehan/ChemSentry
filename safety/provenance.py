"""Provenance model and citation generator for SDS-sourced safety thresholds (M2/M3)."""

from typing import Dict, Optional

# Default supplier authority hierarchy mapping.
# NOTE: reconciliation-policy defaults, not per-chemical safety thresholds -- these
# weight *which source to trust*, they never set a chemical safety limit themselves.
# Unrecognized suppliers fall back to a score below every defined tier (see
# resolve_supplier_authority) so an unmapped name can never silently outrank a
# known-but-low-trust tier.
DEFAULT_AUTHORITY_SCORES: Dict[str, float] = {
    "Primary Manufacturer": 1.0,
    "Authorized Distributor": 0.85,
    "Generic Safety Registry": 0.70,
    "Unverified Third-Party": 0.50,
}
UNRECOGNIZED_SUPPLIER_AUTHORITY = 0.40


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
        "[SDS-ACETONE-2026-v2] Section 7 - Sigma-Aldrich:
         Acetone max_storage_temperature threshold = 25.0 C"
    """
    return (
        f"[{sds_id}] {section_number} - {supplier_name}: "
        f"{chemical_name} {metric_name} threshold = {value} {unit}"
    )


def resolve_supplier_authority(
    supplier_name: str, custom_score: Optional[float] = None
) -> float:
    """Resolve authority score for a given SDS supplier."""
    if custom_score is not None:
        if not 0.0 <= custom_score <= 1.0:
            raise ValueError(
                f"custom_score must be between 0.0 and 1.0, got {custom_score}"
            )
        return custom_score
    return DEFAULT_AUTHORITY_SCORES.get(supplier_name, UNRECOGNIZED_SUPPLIER_AUTHORITY)
