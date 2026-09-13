"""Source authority hierarchy: which source to trust for which question (plan §7).

Our six corpora are not equally authoritative for every question -- a
supplier SDS is preferred for storage conditions, but NIOSH is preferred for
exposure limits. Before this module, two disconnected mechanisms existed
instead of the plan's actual table:
    - `extraction.models.SourceAuthority` -- an enum every extractor in
      `extraction/value_extractor.py` defaults to SUPPLIER_SDS regardless of
      claim type. It tags evidence; nothing consulted a preference order.
    - `safety.provenance.DEFAULT_AUTHORITY_SCORES` -- a supplier *trust-tier*
      table (e.g. "Primary Manufacturer" -> 1.0). This ranks suppliers
      against each other for conflict tie-breaking; it has nothing to do
      with which *kind of source* should be preferred for a given question.

This module is the missing table itself, keyed by `metric_name` (the string
already on `ProvenancedThreshold`, produced by
`agents.agent_a_retrieval.provenance_bridge`) rather than by claim type,
since that's the shape retrieval actually has evidence in by the time
ranking needs to happen.

Honest scope note: the plan's table also names PPE, chemical identity, and
reactivity/incompatibility rows. Those claim types are real extracted
evidence (see `extraction.models.ClaimType`) but are not numeric thresholds
-- `provenance_bridge.to_provenanced_threshold` deliberately excludes them
(a PPE recommendation has no "ceiling" or "floor"). They don't participate
in this ranking mechanism today because nothing routes them through it yet,
not because the hierarchy doesn't apply to them.
"""

from __future__ import annotations

from agents.protocols.schemas import ProvenancedThreshold
from extraction.models import SourceAuthority

# metric_name -> (preferred source, fallback source or None).
# Only covers metrics agents/agent_a_retrieval/provenance_bridge.py actually
# produces (its _THRESHOLD_CLAIM_TYPES keys) -- there is no ranking to do for
# a metric name that can never appear on a ProvenancedThreshold.
_METRIC_AUTHORITY: dict[str, tuple[SourceAuthority, SourceAuthority | None]] = {
    # Storage conditions -- Supplier SDS (Section 7) preferred, NIOSH fallback.
    "max_storage_temperature": (SourceAuthority.SUPPLIER_SDS, SourceAuthority.NIOSH),
    "min_storage_temperature": (SourceAuthority.SUPPLIER_SDS, SourceAuthority.NIOSH),
    "max_storage_humidity": (SourceAuthority.SUPPLIER_SDS, SourceAuthority.NIOSH),
    # Exposure limits -- NIOSH/regulatory preferred, Supplier SDS fallback.
    "exposure_twa": (SourceAuthority.NIOSH, SourceAuthority.SUPPLIER_SDS),
    "exposure_stel": (SourceAuthority.NIOSH, SourceAuthority.SUPPLIER_SDS),
    # Physical properties -- not named in the plan's table; supplier-declared
    # per product, so Supplier SDS is the natural primary with no better-fit
    # fallback among our six corpora.
    "flash_point": (SourceAuthority.SUPPLIER_SDS, None),
    "boiling_point": (SourceAuthority.SUPPLIER_SDS, None),
}
_DEFAULT_AUTHORITY: tuple[SourceAuthority, SourceAuthority | None] = (
    SourceAuthority.SUPPLIER_SDS,
    None,
)


def preferred_source_for_metric(metric_name: str) -> SourceAuthority:
    """Which source tier is preferred as evidence for this metric."""
    return _METRIC_AUTHORITY.get(metric_name, _DEFAULT_AUTHORITY)[0]


def fallback_source_for_metric(metric_name: str) -> SourceAuthority | None:
    """Which source tier to fall back to if the preferred one has no evidence."""
    return _METRIC_AUTHORITY.get(metric_name, _DEFAULT_AUTHORITY)[1]


def rank_by_authority(
    thresholds: list[ProvenancedThreshold],
) -> list[ProvenancedThreshold]:
    """Order thresholds so each one's preferred-tier source sorts first.

    Each threshold is ranked against *its own* metric's preference (a list
    can mix metrics, e.g. a storage-temperature threshold and a boiling-point
    threshold for the same chemical), so this is safe to call on retrieval's
    full result set rather than one metric at a time. A stable sort keeps
    relative order within a tier unchanged (e.g. insertion/document order).

    This governs which evidence Agent A puts first for the reconciler and
    safety layer to consider -- it does not itself resolve a conflict
    between two sources of the *same* tier; that stays
    `agents/agent_b_analysis/reconciler.py`'s job.

    Args:
        thresholds: Retrieved thresholds, possibly spanning several metrics
            and source tiers.

    Returns:
        The same thresholds, reordered.
    """

    def _tier(threshold: ProvenancedThreshold) -> int:
        preferred = preferred_source_for_metric(threshold.metric_name)
        fallback = fallback_source_for_metric(threshold.metric_name)
        if threshold.source_authority == preferred:
            return 0
        if threshold.source_authority == fallback:
            return 1
        return 2

    return sorted(thresholds, key=_tier)
