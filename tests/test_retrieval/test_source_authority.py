"""Unit tests for agents/agent_a_retrieval/source_authority.py (M2, plan §7)."""

from agents.agent_a_retrieval.source_authority import (
    fallback_source_for_metric,
    preferred_source_for_metric,
    rank_by_authority,
)
from agents.protocols.schemas import ProvenancedThreshold, ThresholdDirection
from extraction.models import SourceAuthority


def _threshold(metric_name: str, source_authority: SourceAuthority, sds_id: str):
    return ProvenancedThreshold(
        metric_name=metric_name,
        value=25.0,
        unit="C",
        direction=ThresholdDirection.MAX,
        sds_id=sds_id,
        supplier_name="Test Supplier",
        authority_score=1.0,
        citation=f"[{sds_id}] test citation",
        source_authority=source_authority,
    )


def test_storage_metric_prefers_supplier_sds_with_niosh_fallback() -> None:
    assert (
        preferred_source_for_metric("max_storage_temperature")
        == SourceAuthority.SUPPLIER_SDS
    )
    assert (
        fallback_source_for_metric("max_storage_temperature") == SourceAuthority.NIOSH
    )


def test_exposure_metric_prefers_niosh_with_supplier_sds_fallback() -> None:
    """The plan's table inverts the usual preference here: NIOSH is
    preferred for exposure limits, supplier SDS is only the fallback."""
    assert preferred_source_for_metric("exposure_twa") == SourceAuthority.NIOSH
    assert fallback_source_for_metric("exposure_twa") == SourceAuthority.SUPPLIER_SDS


def test_unmapped_metric_defaults_to_supplier_sds_no_fallback() -> None:
    assert (
        preferred_source_for_metric("some_future_metric")
        == SourceAuthority.SUPPLIER_SDS
    )
    assert fallback_source_for_metric("some_future_metric") is None


def test_rank_by_authority_puts_preferred_tier_first() -> None:
    """For an exposure-limit metric, NIOSH evidence should rank ahead of
    supplier-SDS evidence for the same metric, even though it arrives second."""
    supplier = _threshold("exposure_twa", SourceAuthority.SUPPLIER_SDS, "doc_supplier")
    niosh = _threshold("exposure_twa", SourceAuthority.NIOSH, "doc_niosh")

    ranked = rank_by_authority([supplier, niosh])

    assert [t.sds_id for t in ranked] == ["doc_niosh", "doc_supplier"]


def test_rank_by_authority_handles_mixed_metrics_independently() -> None:
    """A storage-temperature threshold and an exposure-limit threshold have
    opposite preferred tiers -- ranking must respect each threshold's own
    metric, not apply one global preference to the whole list."""
    storage_supplier = _threshold(
        "max_storage_temperature", SourceAuthority.SUPPLIER_SDS, "doc_storage"
    )
    storage_pubchem = _threshold(
        "max_storage_temperature", SourceAuthority.PUBCHEM, "doc_storage_pubchem"
    )
    exposure_niosh = _threshold("exposure_twa", SourceAuthority.NIOSH, "doc_exposure")

    ranked = rank_by_authority([storage_pubchem, exposure_niosh, storage_supplier])

    # storage_supplier (tier 0 for its metric) and exposure_niosh (tier 0 for
    # its metric) both outrank storage_pubchem (tier 2, unranked source).
    assert ranked[-1].sds_id == "doc_storage_pubchem"
    assert {t.sds_id for t in ranked[:2]} == {"doc_storage", "doc_exposure"}
