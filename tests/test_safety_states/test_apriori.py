"""Unit tests for CoStoragePatternMiner and the SDS-backed reactivity checker (M3, Lab 09).

These tests cover the three bugs fixed in feat/agent-b-sds-costorage-lookup:
  1. Absent evidence was returned as "COMPATIBLE" -- now "NO KNOWN WARNING".
  2. 3+ chemical itemsets were checked as a whole frozenset, missing reactive pairs inside.
  3. Case-sensitive matching prevented e.g. "Sodium Hydroxide" from matching "Sodium hydroxide".

New tests use synthetic ProcessedDocuments built from real SDS Section 10 text excerpts
rather than relying on the hand-written KNOWN_INCOMPATIBLE_PAIRS dict.  The miner's
Apriori output (support/confidence/lift) is unchanged; only the labelling logic changed.
"""

from datetime import date

import pytest

from agents.agent_b_analysis.apriori_discovery import (
    CHEMICAL_CLASSES,
    CoStoragePatternMiner,
    _check_pair_against_sds,
    _normalise,
    _split_incompat_value,
    check_itemset_reactivity,
)
from extraction.models import (
    ClaimType,
    ExtractionMethod,
    ExtractionResult,
    ProcessedDocument,
    SDSMetadata,
    SourceAuthority,
)

# ---------------------------------------------------------------------------
# Helpers to build synthetic ProcessedDocuments
# ---------------------------------------------------------------------------


def _make_doc(
    chemical_name: str,
    document_id: str,
    supplier: str,
    incompat_values: list[str],
) -> ProcessedDocument:
    """Build a minimal ProcessedDocument with the given INCOMPATIBILITY claims."""
    extractions = [
        ExtractionResult(
            chemical=chemical_name,
            claim_type=ClaimType.INCOMPATIBILITY,
            value=v,
            unit="",
            document_id=document_id,
            supplier=supplier,
            section_number=10,
            original_text_span=v[:200],
            extraction_method=ExtractionMethod.REGEX,
            confidence=0.80,
            source_authority=SourceAuthority.SUPPLIER_SDS,
        )
        for v in incompat_values
    ]
    return ProcessedDocument(
        metadata=SDSMetadata(
            document_id=document_id,
            chemical_name=chemical_name,
            supplier=supplier,
            retrieval_date=date.today(),
        ),
        sections={10: " ".join(incompat_values)},
        extractions=extractions,
        tokens=[],
    )


# ---------------------------------------------------------------------------
# Real SDS text excerpts (taken from real corpus, verified this session)
# ---------------------------------------------------------------------------

# Sigma-Aldrich sodium hydroxide [221465] Section 10 lists (among others):
#   Acetone, sulfuric acid, hydrogen halides, ...
_NAOH_DOC = _make_doc(
    chemical_name="Sodium hydroxide",
    document_id="221465",
    supplier="Sigma-Aldrich",
    incompat_values=[
        "Acetone, Chlorine, Hydrogen peroxide, Maleic anhydride",
        "sulfuric acid, Nitric acid",
        "Hydrogen halides",
    ],
)

# Synthetic doc for Hydrochloric acid -- no real incompatibility listing for NaOH
# by name, but NaOH lists "Hydrogen halides" and HCl is in CHEMICAL_CLASSES as a
# hydrogen halide.
_HCL_DOC = _make_doc(
    chemical_name="Hydrochloric acid",
    document_id="TEST_HCL_001",
    supplier="Test Supplier",
    incompat_values=[
        "Oxidizing agents, Alkalis",
    ],
)


@pytest.fixture
def miner_no_docs() -> CoStoragePatternMiner:
    """Miner with no corpus -- exercises the fallback dict path."""
    return CoStoragePatternMiner(min_support=0.2, min_threshold_lift=1.0, documents=[])


@pytest.fixture
def miner_with_naoh() -> CoStoragePatternMiner:
    """Miner with the synthetic sodium hydroxide SDS loaded."""
    return CoStoragePatternMiner(
        min_support=0.2, min_threshold_lift=1.0, documents=[_NAOH_DOC]
    )


@pytest.fixture
def miner_with_both_docs() -> CoStoragePatternMiner:
    """Miner with both the NaOH and HCl docs loaded."""
    return CoStoragePatternMiner(
        min_support=0.2,
        min_threshold_lift=1.0,
        documents=[_NAOH_DOC, _HCL_DOC],
    )


# ---------------------------------------------------------------------------
# Structural tests -- rule shape unchanged
# ---------------------------------------------------------------------------


def test_discover_co_storage_rules_returns_list(miner_no_docs: CoStoragePatternMiner):
    """Apriori returns a list of dicts with all expected keys."""
    transactions = [
        ["Sodium hydroxide", "Acetone"],
        ["Sodium hydroxide", "Acetone"],
        ["Sodium hydroxide", "Acetone"],
    ]
    rules = miner_no_docs.discover_co_storage_rules(transactions)
    assert isinstance(rules, list)
    assert len(rules) > 0
    rule = rules[0]
    assert "antecedents" in rule
    assert "consequents" in rule
    assert "support" in rule
    assert "confidence" in rule
    assert "lift" in rule
    assert "incompatibility_status" in rule


def test_empty_transactions_returns_empty(miner_no_docs: CoStoragePatternMiner):
    """Empty transaction list returns an empty list without raising."""
    assert miner_no_docs.discover_co_storage_rules([]) == []


# ---------------------------------------------------------------------------
# Bug 1: No COMPATIBLE as default -- absence of evidence is NOT safe
# ---------------------------------------------------------------------------


def test_pair_with_no_evidence_returns_no_known_warning(
    miner_no_docs: CoStoragePatternMiner,
):
    """A pair absent from both the SDS corpus and the fallback dict must NOT be
    reported as COMPATIBLE.  It must receive "NO KNOWN WARNING" to make clear that
    the system found no evidence, not that the pair has been verified safe.

    Acceptance criterion (task spec): 'A pair with no Section 10 evidence either way
    gets the "no known warning" status, not "compatible".'
    """
    # "Water" and "Sand" have no SDS docs and are not in _CITED_FALLBACK_PAIRS.
    transactions = [["Water", "Sand"], ["Water", "Sand"], ["Water", "Sand"]]
    rules = miner_no_docs.discover_co_storage_rules(transactions)
    for rule in rules:
        status = rule["incompatibility_status"]
        assert (
            "COMPATIBLE" not in status
        ), f"'COMPATIBLE' must never appear as a default -- got: {status!r}"
        assert (
            "NO KNOWN WARNING" in status
        ), f"Expected 'NO KNOWN WARNING' for unknown pair, got: {status!r}"


# ---------------------------------------------------------------------------
# Bug 2: Pair-by-pair checking inside itemsets
# ---------------------------------------------------------------------------


def test_reactive_pair_inside_3way_itemset_is_flagged(
    miner_with_naoh: CoStoragePatternMiner,
):
    """A 3-chemical itemset must be flagged if ANY internal pair is reactive.

    Acceptance criterion (task spec): 'Any itemset containing Sodium hydroxide +
    Sulfuric acid is flagged, naming that pair.'

    Before the fix, only the whole itemset frozenset was compared; {NaOH, H2SO4, X}
    would never match the 2-element key {NaOH, H2SO4} in KNOWN_INCOMPATIBLE_PAIRS.
    """
    status = check_itemset_reactivity(
        ["Sodium hydroxide", "Sulfuric acid", "Acetone"],
        [_NAOH_DOC],
    )
    assert "COMPATIBLE" not in status
    # Must name the reactive pair
    assert (
        "Sodium hydroxide" in status or "sulfuric acid" in status.lower()
    ), f"Expected the reactive pair to be named, got: {status!r}"
    assert (
        "REACTIVE" in status or "VIOLENT REACTION" in status
    ), f"Expected REACTIVE or VIOLENT REACTION prefix, got: {status!r}"


def test_fallback_dict_flagged_for_sulfuric_acid_naoh_pair_no_docs(
    miner_no_docs: CoStoragePatternMiner,
):
    """With no corpus, the fallback dict must flag Sodium hydroxide + Sulfuric acid.

    Acceptance criterion: any itemset containing Sodium hydroxide + Sulfuric acid
    is flagged, naming that pair.
    """
    transactions = [
        ["Sodium hydroxide", "Sulfuric acid"],
        ["Sodium hydroxide", "Sulfuric acid"],
        ["Sodium hydroxide", "Sulfuric acid"],
    ]
    rules = miner_no_docs.discover_co_storage_rules(transactions)
    flagged = [
        r
        for r in rules
        if (
            "VIOLENT REACTION" in r["incompatibility_status"]
            or "REACTIVE" in r["incompatibility_status"]
        )
    ]
    assert flagged, f"Expected at least one rule flagging the pair. Rules: {rules}"


# ---------------------------------------------------------------------------
# Bug 3: Case-insensitive matching
# ---------------------------------------------------------------------------


def test_case_difference_does_not_change_result(miner_with_naoh: CoStoragePatternMiner):
    """'Sodium Hydroxide' and 'Sodium hydroxide' must produce the same status.

    Acceptance criterion (task spec): 'Case differences ("Sodium Hydroxide" vs
    "Sodium hydroxide") don't change the result.'
    """
    status_lower = check_itemset_reactivity(
        ["Sodium hydroxide", "Acetone"], [_NAOH_DOC]
    )
    status_title = check_itemset_reactivity(
        ["Sodium Hydroxide", "Acetone"], [_NAOH_DOC]
    )
    # Both must agree on whether a warning exists
    assert ("NO KNOWN WARNING" in status_lower) == (
        "NO KNOWN WARNING" in status_title
    ), f"Case difference changed result:\n  lower: {status_lower!r}\n  title: {status_title!r}"
    assert (
        "REACTIVE" in status_lower or "REVIEW" in status_lower
    ), f"Expected REACTIVE or REVIEW for NaOH+Acetone, got: {status_lower!r}"


# ---------------------------------------------------------------------------
# Sodium hydroxide + Acetone -- real SDS citation test
# ---------------------------------------------------------------------------


def test_sodium_hydroxide_acetone_flagged_with_citation(
    miner_with_naoh: CoStoragePatternMiner,
):
    """Sodium hydroxide + Acetone must be flagged with a citation to the sodium
    hydroxide SDS.

    Acceptance criterion (task spec): 'Sodium hydroxide + Acetone is flagged with
    a citation to the sodium hydroxide SDS.'
    """
    status = check_itemset_reactivity(["Sodium hydroxide", "Acetone"], [_NAOH_DOC])
    assert "REACTIVE" in status, f"Expected REACTIVE, got: {status!r}"
    # Citation must include the document_id
    assert "221465" in status, f"Expected citation to SDS [221465], got: {status!r}"


# ---------------------------------------------------------------------------
# Hydrochloric acid + Sodium hydroxide -- class-level REVIEW (never COMPATIBLE)
# ---------------------------------------------------------------------------


def test_hcl_naoh_never_compatible(miner_with_both_docs: CoStoragePatternMiner):
    """Hydrochloric acid + Sodium hydroxide must never be reported as COMPATIBLE.

    Acceptance criterion (task spec): 'Hydrochloric acid + Sodium hydroxide is never
    COMPATIBLE (REVIEW or reactive, with citation).'

    NaOH's SDS lists "Hydrogen halides" as incompatible.  HCl is a hydrogen halide
    per CHEMICAL_CLASSES (cited to CAMEO + IUPAC).  This triggers a REVIEW at minimum.
    """
    status = check_itemset_reactivity(
        ["Hydrochloric acid", "Sodium hydroxide"],
        [_NAOH_DOC, _HCL_DOC],
    )
    assert (
        "COMPATIBLE" not in status
    ), f"'COMPATIBLE' must never appear for HCl + NaOH. Got: {status!r}"
    assert (
        "REVIEW" in status or "REACTIVE" in status
    ), f"Expected REVIEW or REACTIVE for HCl + NaOH, got: {status!r}"


# ---------------------------------------------------------------------------
# _normalise helper
# ---------------------------------------------------------------------------


def test_normalise_collapses_case_and_whitespace():
    assert _normalise("  Sodium  Hydroxide  ") == "sodium hydroxide"
    assert _normalise("SULFURIC ACID") == "sulfuric acid"
    assert _normalise("hydrochloric acid") == "hydrochloric acid"


# ---------------------------------------------------------------------------
# _split_incompat_value -- noise filtering
# ---------------------------------------------------------------------------


def test_split_incompat_value_strips_leading_with():
    parts = _split_incompat_value("with: sodium hydroxide, acids")
    assert any("sodium hydroxide" in p.lower() for p in parts)
    assert any("acids" in p.lower() for p in parts)


def test_split_incompat_value_discards_page_footer():
    parts = _split_incompat_value("Acetone, Sigma- S5761 Page 5 of 10, Chlorine")
    assert not any(
        "Page" in p for p in parts
    ), f"Page footer should be discarded, got: {parts}"
    assert any("Acetone" in p for p in parts)
    assert any("Chlorine" in p for p in parts)


def test_split_incompat_value_discards_digit_only_tokens():
    parts = _split_incompat_value("Acetone, 1234, Chlorine")
    assert not any(p.strip().isdigit() for p in parts)
    assert any("Acetone" in p for p in parts)


# ---------------------------------------------------------------------------
# CHEMICAL_CLASSES table sanity
# ---------------------------------------------------------------------------


def test_chemical_classes_contains_expected_entries():
    """Spot-check that key chemicals are in the CHEMICAL_CLASSES table."""
    assert "hydrochloric acid" in CHEMICAL_CLASSES
    assert "hydrogen halides" in CHEMICAL_CLASSES["hydrochloric acid"]
    assert "sulfuric acid" in CHEMICAL_CLASSES
    assert "sodium hydroxide" in CHEMICAL_CLASSES
    assert "bases" in CHEMICAL_CLASSES["sodium hydroxide"]


# ---------------------------------------------------------------------------
# Regression guard: original corpus-verified pairs still flagged without docs
# ---------------------------------------------------------------------------


def test_regression_sodium_hydroxide_acetone_flagged_no_docs(
    miner_no_docs: CoStoragePatternMiner,
):
    """Regression guard: Sodium hydroxide + Acetone must be flagged even when no
    corpus documents are loaded (fallback dict path).

    This replaces test_incompatible_pair_flagging_uses_real_corpus_chemicals from
    the old test suite.  The fallback dict still references corpus/raw/ in the
    citation string; the test verifies the status starts with REACTIVE and contains
    "221465" (the real SDS document ID).
    """
    transactions = [
        ["Sodium hydroxide", "Acetone"],
        ["Sodium hydroxide", "Acetone"],
        ["Sodium hydroxide", "Acetone"],
    ]
    rules = miner_no_docs.discover_co_storage_rules(transactions)
    flagged = next(
        (
            r
            for r in rules
            if "REACTIVE" in r["incompatibility_status"]
            and "221465" in r["incompatibility_status"]
        ),
        None,
    )
    assert (
        flagged is not None
    ), f"Expected REACTIVE rule citing [221465] via fallback dict. Got: {rules}"


# ---------------------------------------------------------------------------

# Named entries outrank class entries; class labels match whole words only

# ---------------------------------------------------------------------------


# Order as in the real sodium hydroxide SDS [221465] Section 10: the class

# "Acids" comes before "sulfuric acid" by name.

_NAOH_CLASS_FIRST_DOC = _make_doc(
    chemical_name="Sodium hydroxide",
    document_id="221465",
    supplier="Sigma-Aldrich",
    incompat_values=["Acetone, Hydrogen halides, Acids, sulfuric acid, Water"],
)


# Real acetone SDS [179124] Section 10 lists "Alkali metals" and

# "Strong oxidizing agents".

_ACETONE_DOC = _make_doc(
    chemical_name="Acetone",
    document_id="179124",
    supplier="Sigma-Aldrich",
    incompat_values=["Strong oxidizing agents, Alkali metals"],
)


def test_named_entry_beats_an_earlier_class_entry_in_the_same_sds():
    """Regression: "Acids" came first, so NaOH + sulfuric acid was REVIEW

    although the same SDS names sulfuric acid explicitly."""

    status = _check_pair_against_sds(
        "Sodium hydroxide", "Sulfuric acid", [_NAOH_CLASS_FIRST_DOC]
    )

    assert status is not None

    assert status.startswith("REACTIVE:"), status

    assert "sulfuric acid" in status


def test_named_entry_in_either_sds_beats_a_class_entry_in_the_other():
    """Regression: acetone's SDS was checked first and its "Alkali metals"

    entry won, although NaOH's SDS names acetone explicitly."""

    status = _check_pair_against_sds(
        "Acetone", "Sodium hydroxide", [_ACETONE_DOC, _NAOH_CLASS_FIRST_DOC]
    )

    assert status is not None

    assert status.startswith("REACTIVE:"), status

    assert "[221465]" in status


def test_alkali_metals_is_not_a_class_sodium_hydroxide_belongs_to():
    """Sodium hydroxide is an alkali-metal hydroxide, not an alkali metal."""

    assert (
        _check_pair_against_sds("Acetone", "Sodium hydroxide", [_ACETONE_DOC]) is None
    )


def test_class_label_matches_as_whole_words_inside_a_longer_entry():
    """ "Strong oxidizing agents" names the class potassium permanganate's own

    SDS puts it in (Oxidizing solids, H272): a REVIEW, not a REACTIVE."""

    status = _check_pair_against_sds(
        "Acetone", "Potassium permanganate", [_ACETONE_DOC]
    )

    assert status is not None

    assert status.startswith("REVIEW:"), status


def test_class_tables_hold_only_plural_class_nouns():
    """A singular label such as "alkali" or "acid" would match an unrelated

    class ("Alkali metals", "Acid anhydrides")."""

    for name, classes in CHEMICAL_CLASSES.items():

        for label in classes:

            assert label.endswith("s"), f"{name}: {label!r}"


def test_itemset_status_starts_with_its_status_word():
    """Consumers (the UI panel, the LLM tool) read the word before the first
    ":"; a REVIEW used to come back as "[pair A + B] REVIEW: ..."."""
    status = check_itemset_reactivity(
        ["Hydrochloric acid", "Sodium hydroxide"], [_NAOH_CLASS_FIRST_DOC]
    )
    assert status.startswith("REVIEW:"), status
    assert status.endswith("[pair: Hydrochloric acid + Sodium hydroxide]"), status
