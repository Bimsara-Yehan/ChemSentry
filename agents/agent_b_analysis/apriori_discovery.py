"""Co-Storage Association Discovery using mlxtend Apriori and association rules (M3, Lab 09).

Framed as discovery of co-occurring storage patterns, NOT direct hazard classification.
Identified rules are cross-referenced with real SDS Section 10 incompatibility claims
extracted from the corpus (extraction.models.ClaimType.INCOMPATIBILITY), not against a
hand-written lookup table.

Architecture note
-----------------
This module is deliberately NOT a safety-decision component: Apriori discovers *patterns*;
the reactivity check below classifies those patterns using cited evidence from real SDS
documents.  The status vocabulary communicates the *quality of evidence* rather than
collapsing it into a binary safe/unsafe verdict:

  "REACTIVE: ..."          -- at least one real SDS Section 10 source names the other
                              chemical explicitly as incompatible.
  "VIOLENT REACTION: ..."  -- as REACTIVE but for violent exothermic / explosive reactions.
                              Only the cited fallback dict uses it: SDS Section 10 text
                              names incompatible materials without grading severity, so
                              the corpus path reports REACTIVE.
  "REVIEW: ..."            -- a real SDS lists an incompatibility *class* (e.g. "Bases",
                              "Hydrogen halides") rather than the chemical by name; a
                              human reviewer must confirm membership.

An exact name match in either chemical's SDS always outranks a class match in either:
"Sodium hydroxide" lists both the class "Acids" and "sulfuric acid" by name, and the
named entry is the stronger, citable evidence.
  "NO KNOWN WARNING: ..."  -- neither SDS Section 10 mentions the other chemical or any
                              class we can evaluate without guessing.  This replaces the
                              old "COMPATIBLE" default which incorrectly treated absence
                              of evidence as positive evidence of safety.

Hard constraints (CLAUDE.md)
-----------------------------
- Wildcard / suffix matching is retrieval, NOT classification.  We NEVER decide that
  "Hydrochloric acid" is an acid from its name.  Every class membership entry in
  CHEMICAL_CLASSES below must cite a real source.
- Fuzzy matching (Soundex, edit-distance) is NOT used here, for the same reason M2's
  threshold retrieval only accepts exact names: a wrong fuzzy match would *invent* a
  hazard or *hide* one.  We normalise only case and whitespace.  Class labels match as
  whole words inside an entry ("Strong oxidizing agents" contains "oxidizing agents"),
  never as a fragment of a longer word, and CHEMICAL_CLASSES holds only plural class
  nouns ("alkalis", not "alkali", which would match "Alkali metals").
- Unknown must stay unknown.  If there is no evidence of incompatibility in the SDS
  corpus we say "NO KNOWN WARNING", never "COMPATIBLE".
"""

from __future__ import annotations

import re
from itertools import combinations
from typing import Any, Optional

import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder

from extraction.models import ClaimType, ProcessedDocument

# ---------------------------------------------------------------------------
# Cited fallback dict  (used only when the corpus is empty, e.g. CI runs)
# ---------------------------------------------------------------------------
#
# Every entry must be cross-referenceable to a real document in corpus/raw/.
# Keys are frozensets of *normalised* (lower-cased, whitespace-collapsed) chemical
# names so that matching is case-insensitive.
#
# The three original general-knowledge entries have been REMOVED because none of
# their chemicals has an SDS in corpus/raw/:
#   Nitric Acid / Ethanol       -- no Nitric Acid SDS in corpus/raw/
#   Sodium Cyanide / Sulfuric Acid -- no Sodium Cyanide SDS in corpus/raw/
#   Ammonium Nitrate / Fuel Oil -- no Ammonium Nitrate or Fuel Oil SDS in corpus/raw/
#
# DO NOT add entries here without citing the exact SDS document_id and section.

_CITED_FALLBACK_PAIRS: dict[frozenset, str] = {
    frozenset(["sodium hydroxide", "acetone"]): (
        "REACTIVE: real Section 10 data (Sigma-Aldrich sodium hydroxide SDS [221465]) "
        "lists Acetone as an incompatible material"
    ),
    frozenset(["sodium hydroxide", "sulfuric acid"]): (
        "VIOLENT REACTION: real Section 10 data (Sigma-Aldrich sodium hydroxide SDS "
        "[221465]) lists sulfuric acid as an incompatible material -- strong base + "
        "strong acid, exothermic neutralisation"
    ),
    frozenset(["ethanol", "potassium permanganate"]): (
        "REACTIVE: real Section 10 data (ethanol SDS, corpus/raw/) lists potassium "
        "permanganate as an incompatible material -- strong oxidizer + organic flammable "
        "liquid"
    ),
    frozenset(["zinc oxide", "hydrogen peroxide solution"]): (
        "REACTIVE: real Section 10 data (zinc oxide SDS, corpus/raw/) lists hydrogen "
        "peroxide as an incompatible material"
    ),
    frozenset(["sodium hydroxide", "hydrochloric acid"]): (
        "REVIEW: real Section 10 data (Sigma-Aldrich sodium hydroxide SDS [221465]) "
        "lists 'hydrogen halides' as incompatible; hydrochloric acid belongs to this class"
    ),
}

# ---------------------------------------------------------------------------
# Chemical class membership table
# ---------------------------------------------------------------------------
#
# SDS Section 10 often names *classes* of incompatible materials rather than individual
# chemicals (e.g. "Hydrogen halides", "Acids", "Reducing agents").  We CANNOT resolve
# class membership from a chemical name alone (CLAUDE.md: no suffix/wildcard
# classification).  Instead this reviewed table maps normalised chemical names to the
# class labels that appear in real SDS Section 10 text.
#
# Each entry says where its membership comes from, in one of two tiers:
#   - "SDS": the chemical's own SDS in corpus/raw/ states it (GHS class in Section 2).
#   - "Textbook": standard chemistry the SDS does not state (e.g. that sodium hydroxide
#     is a strong base). Acceptable only because a class match is REVIEW, never
#     REACTIVE -- a person confirms it.
# Do NOT add entries inferred from the chemical's name alone, and use plural class nouns
# only: a singular such as "alkali" would match the unrelated class "Alkali metals".

_OXIDISER_CLASSES = {"oxidizing agents", "oxidising agents", "oxidizers", "oxidisers"}

CHEMICAL_CLASSES: dict[str, set[str]] = {
    # Textbook: a strong mineral acid; aqueous hydrogen chloride, which is why sodium
    # hydroxide's "Hydrogen halides" entry is worth a person's review.
    "hydrochloric acid": {"acids", "strong acids", "hydrogen halides"},
    # Textbook: a strong mineral acid, and an oxidising acid when concentrated. Its SDS
    # (258105) classes it as corrosive (H290), not as an oxidiser.
    "sulfuric acid": {"acids", "strong acids"} | _OXIDISER_CLASSES,
    # Textbook: a strong base and an alkali-metal hydroxide (acetone's SDS lists
    # "alkali hydroxides"). Its SDS (221465) classes it as corrosive only.
    "sodium hydroxide": {"bases", "strong bases", "alkalis", "alkali hydroxides"},
    # Textbook: a weak base (a hydrogen carbonate salt).
    "sodium bicarbonate": {"bases", "carbonates"},
    # Textbook: a weak organic (carboxylic) acid.
    "citric acid": {"acids", "organic acids"},
    # SDS: "Flammable liquids, Category 2, H225" (179124). Textbook: a ketone solvent.
    "acetone": {"flammable liquids", "ketones", "organic solvents"},
    # SDS: "Flammable liquids, Category 2, H225" (51976, ethanol_en). Textbook: an
    # alcohol solvent.
    "ethanol": {"flammable liquids", "alcohols", "organic solvents"},
    # SDS: "Flammable liquids, Category 2, H225" (650447, i9516, sds_631090_en_gb).
    # Textbook: an alcohol solvent.
    "2-propanol": {"flammable liquids", "alcohols", "organic solvents"},
    # SDS: "Oxidizing solids, Category 2, H272: May intensify fire; oxidizer" (238511).
    "potassium permanganate": set(_OXIDISER_CLASSES),
    # SDS: "Ox. Liq. 1; H271" for the hydrogen peroxide component (216763, 16911).
    "hydrogen peroxide solution": set(_OXIDISER_CLASSES),
}


def _normalise(name: str) -> str:
    """Normalise a chemical name for case/whitespace-insensitive comparison.

    Uses only case folding and whitespace collapsing -- no stemming, no fuzzy
    matching -- to prevent accidentally equating different chemicals (CLAUDE.md:
    wildcard / suffix matching is retrieval, not classification).
    """
    return re.sub(r"\s+", " ", name.strip().lower())


def _split_incompat_value(raw: str) -> list[str]:
    """Split a raw INCOMPATIBILITY claim value into individual candidate entries.

    Real SDS Section 10 incompatibility text is noisy (M1 known data-quality issue):
      - Leading "with:" prefixes (e.g. "with: sodium hydroxide, acids")
      - Page footers like "Sigma- S5761 Page 5 of 10"
      - Multiple substances on one line separated by commas or newlines

    We split on commas/newlines and strip obvious non-chemical tokens.  We do NOT
    attempt to fix M1 extractor bugs -- only filter well-understood noise patterns.
    Problems encountered in practice are listed in the PR description for M1.
    """
    # Remove a leading "with:" or "with " prefix from the whole value
    cleaned = re.sub(r"^\s*with\s*:?\s*", "", raw, flags=re.IGNORECASE)

    # Split on commas and newlines
    parts = re.split(r"[,\n]+", cleaned)

    results: list[str] = []
    for part in parts:
        part = part.strip()
        # Discard page headers/footers: "Page 5 of 10", "Sigma- S5761 Page 5 of 10"
        if re.search(r"\bPage\s+\d+\s+of\s+\d+\b", part, re.IGNORECASE):
            continue
        # Discard tokens that are only digits, punctuation, or whitespace
        if re.fullmatch(r"[\d\s\-\u2013\u2014]+", part):
            continue
        if len(part) >= 3:
            results.append(part)
    return results


def _check_pair_against_sds(
    chem_a: str,
    chem_b: str,
    documents: list[ProcessedDocument],
) -> Optional[str]:
    """Look up incompatibility evidence for a chemical pair using SDS Section 10 data.

    Why this function exists (bugs it fixes)
    ----------------------------------------
    The previous implementation compared the *entire* Apriori frozenset against a
    hand-written dict using exact frozenset equality.  That had three bugs:

      1. A pair absent from the dict returned "COMPATIBLE" -- absence of evidence is
         NOT evidence of safety (CLAUDE.md: unknown must stay unknown).
      2. A 3+ chemical itemset was checked only as a whole, never pair-by-pair, so a
         known incompatible pair inside a 3-way itemset was silently missed.
      3. Matching was case-sensitive ("Sodium hydroxide" != "Sodium Hydroxide").

    Algorithm
    ---------
    For the pair (A, B):
      1. Exact case-insensitive name match: does A's SDS Section 10 list B by name?
         Or does B's SDS Section 10 list A by name?  Both SDSs are searched for a
         named entry before any class match is considered, because a class entry
         often comes first in the same list: sodium hydroxide's Section 10 lists
         "Acids" before "sulfuric acid", and stopping at the class would downgrade a
         named, citable incompatibility to REVIEW.
      2. Class-level match (REVIEW): does A's SDS list a class that B belongs to per
         CHEMICAL_CLASSES?  Or vice versa?  Labels match as whole words and are tried
         in sorted order, so the same pair always gets the same cited reason.
      3. If neither chemical has an SDS in the loaded corpus, fall back to the
         _CITED_FALLBACK_PAIRS dict (CI / empty corpus safety net).

    Args:
        chem_a: First chemical name (as stored in the zone inventory).
        chem_b: Second chemical name.
        documents: All ProcessedDocuments loaded from corpus/raw/ at startup.
                   An empty list is valid (empty corpus in CI).

    Returns:
        A status string starting with "REACTIVE:", "VIOLENT REACTION:", or "REVIEW:",
        or None if no evidence found.  None -> the caller returns "NO KNOWN WARNING".
    """
    norm_a = _normalise(chem_a)
    norm_b = _normalise(chem_b)

    sds_for_a: list[ProcessedDocument] = []
    sds_for_b: list[ProcessedDocument] = []

    for doc in documents:
        doc_chem = _normalise(doc.metadata.chemical_name)
        if doc_chem == norm_a:
            sds_for_a.append(doc)
        elif doc_chem == norm_b:
            sds_for_b.append(doc)

    def _entries(source_docs: list[ProcessedDocument]):
        """Yield (entry, normalised entry, document_id, supplier) per Section 10 item."""
        for doc in source_docs:
            for er in doc.extractions:
                if er.claim_type != ClaimType.INCOMPATIBILITY:
                    continue
                for entry in _split_incompat_value(er.value):
                    yield entry, _normalise(entry), er.document_id, er.supplier

    def _named_in(
        source_docs: list[ProcessedDocument], norm_target: str, source_chem_name: str
    ) -> Optional[str]:
        """REACTIVE if source_docs' Section 10 names the other chemical exactly."""
        for entry, norm_entry, doc_id, supplier in _entries(source_docs):
            if norm_entry == norm_target:
                return (
                    f"REACTIVE: [{doc_id}] Section 10 - {supplier}: "
                    f"{source_chem_name} lists {entry!r} as incompatible material"
                )
        return None

    def _class_in(
        source_docs: list[ProcessedDocument],
        target_classes: set[str],
        source_chem_name: str,
        other_chem_name: str,
    ) -> Optional[str]:
        """REVIEW if source_docs' Section 10 names a class the other chemical is in.

        We never infer class from the chemical name (CLAUDE.md); membership comes
        only from CHEMICAL_CLASSES, where every entry states its source.
        """
        for entry, norm_entry, doc_id, supplier in _entries(source_docs):
            for cls in sorted(target_classes):
                if norm_entry == cls:
                    return (
                        f"REVIEW: [{doc_id}] Section 10 - {supplier}: "
                        f"{source_chem_name} lists the class '{entry}'; "
                        f"check whether {other_chem_name} belongs to it"
                    )
                # Whole-word match inside a longer entry, e.g. "Strong oxidizing
                # agents" contains "oxidizing agents".
                if re.search(rf"\b{re.escape(cls)}\b", norm_entry):
                    return (
                        f"REVIEW: [{doc_id}] Section 10 - {supplier}: "
                        f"{source_chem_name} mentions '{entry}', which names the "
                        f"class '{cls}' that {other_chem_name} belongs to -- "
                        f"verify membership"
                    )
        return None

    classes_a = CHEMICAL_CLASSES.get(norm_a, set())
    classes_b = CHEMICAL_CLASSES.get(norm_b, set())

    # Pass 1: a named entry in either SDS (strongest, citable evidence).
    result = _named_in(sds_for_a, norm_b, chem_a) or _named_in(
        sds_for_b, norm_a, chem_b
    )
    if result:
        return result

    # Pass 2: a class entry in either SDS (needs a person to confirm membership).
    result = _class_in(sds_for_a, classes_b, chem_a, chem_b) or _class_in(
        sds_for_b, classes_a, chem_b, chem_a
    )
    if result:
        return result

    # Neither chemical has an SDS in the corpus -- use cited fallback dict
    if not sds_for_a and not sds_for_b:
        norm_pair = frozenset([norm_a, norm_b])
        fallback = _CITED_FALLBACK_PAIRS.get(norm_pair)
        if fallback:
            return fallback

    return None


def check_itemset_reactivity(
    itemset: list[str],
    documents: list[ProcessedDocument],
) -> str:
    """Determine the reactivity status for a set of co-stored chemicals.

    Why we check every pair inside the itemset (bug fix)
    ----------------------------------------------------
    The old code did KNOWN_INCOMPATIBLE_PAIRS.get(frozenset(itemset), ...) which only
    matched if the *entire* itemset was exactly one dict key.  A 3-chemical itemset
    {A, B, C} would never match {A, B} even when A+B was a known VIOLENT REACTION.
    This function checks every pair inside the itemset.

    Args:
        itemset: Combined antecedent + consequent chemicals from one Apriori rule.
        documents: ProcessedDocuments from the loaded corpus (may be empty in CI).

    Returns:
        "REACTIVE: ..."          -- cited SDS evidence of reactive pair.
        "VIOLENT REACTION: ..."  -- cited SDS evidence of violent reaction pair.
        "REVIEW: ..."            -- class-level review needed for at least one pair.
        "NO KNOWN WARNING: ..."  -- no SDS evidence for any pair.  NOT "compatible".
    """
    if len(itemset) < 2:
        return (
            "NO KNOWN WARNING: no co-storage pair to evaluate "
            "(single-item itemset; Apriori support/confidence unchanged)"
        )

    review_statuses: list[str] = []

    for chem_a, chem_b in combinations(sorted(itemset), 2):
        status = _check_pair_against_sds(chem_a, chem_b, documents)
        if status is None:
            continue
        # REACTIVE or VIOLENT REACTION -> return immediately naming the pair
        if status.startswith("REACTIVE:") or status.startswith("VIOLENT REACTION:"):
            pair_label = f"{chem_a} + {chem_b}"
            return f"{status} [pair: {pair_label}]"
        if status.startswith("REVIEW:"):
            # Pair label goes last, as for REACTIVE: consumers read the status
            # word before the first ":" (ui/src/components/CoStoragePanel.jsx).
            review_statuses.append(f"{status} [pair: {chem_a} + {chem_b}]")

    if review_statuses:
        # Surface the first (and most important) REVIEW
        return review_statuses[0]

    return (
        "NO KNOWN WARNING: no incompatibility listed in the available "
        "SDS Section 10 data for any pair in this itemset"
    )


class CoStoragePatternMiner:
    """Discovers co-stored chemical itemsets across warehouse zones using Apriori (Lab 09).

    Why Apriori rather than a pairwise scan
    ----------------------------------------
    Apriori (mlxtend, Lab 09) surfaces *frequent* co-storage patterns with support and
    confidence metrics that a pairwise scan does not provide.  High-lift rules indicate
    chemicals that appear together more often than chance -- valuable for inventory
    auditing even when no reactivity risk is flagged.  The reactivity check is applied
    *after* Apriori discovers the patterns (CLAUDE.md: "Apriori discovers co-storage
    patterns, not hazards").

    Args:
        min_support: Minimum support threshold for the Apriori algorithm.
        min_threshold_lift: Minimum lift for association rule generation.
        documents: Already-extracted ProcessedDocuments to consult for SDS Section 10
                   incompatibility data.  At runtime pass api.main._PROCESSED_DOCUMENTS;
                   omit or pass [] to use the cited fallback dict only (CI default).
    """

    def __init__(
        self,
        min_support: float = 0.2,
        min_threshold_lift: float = 1.0,
        documents: Optional[list[ProcessedDocument]] = None,
    ) -> None:
        self.min_support = min_support
        self.min_threshold_lift = min_threshold_lift
        self._documents: list[ProcessedDocument] = (
            documents if documents is not None else []
        )

    def discover_co_storage_rules(
        self, transactions: list[list[str]]
    ) -> list[dict[str, Any]]:
        """Mine frequent itemsets and association rules from zone co-storage transactions.

        The Apriori mining step (support/confidence/lift values) is UNCHANGED from the
        original implementation.  Only the incompatibility_status labelling has changed.

        Returns:
            List of rule dicts with keys: antecedents, consequents, support, confidence,
            lift, incompatibility_status.
        """
        if not transactions:
            return []

        te = TransactionEncoder()
        te_ary = te.fit(transactions).transform(transactions)
        df = pd.DataFrame(te_ary, columns=te.columns_)

        frequent_itemsets = apriori(df, min_support=self.min_support, use_colnames=True)
        if frequent_itemsets.empty:
            return []

        rules = association_rules(
            frequent_itemsets, metric="lift", min_threshold=self.min_threshold_lift
        )
        discovered_rules = []

        for _, row in rules.iterrows():
            antecedents = list(row["antecedents"])
            consequents = list(row["consequents"])
            combined_itemset = antecedents + consequents

            incompatibility_status = check_itemset_reactivity(
                combined_itemset, self._documents
            )

            discovered_rules.append(
                {
                    "antecedents": antecedents,
                    "consequents": consequents,
                    "support": round(float(row["support"]), 4),
                    "confidence": round(float(row["confidence"]), 4),
                    "lift": round(float(row["lift"]), 4),
                    "incompatibility_status": incompatibility_status,
                }
            )

        return discovered_rules
