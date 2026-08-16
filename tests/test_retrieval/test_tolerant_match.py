"""Tests for the tolerant retrieval cascade (Lab 04 / L3).

Mirrors the evaluation table in ChemSentry_Final_Plan.md Part VIII Layer 2: clean
input, 1 typo, 2 typos, unresolvable.
"""

from agents.agent_a_retrieval.kgram_index import KGramIndex
from agents.agent_a_retrieval.tolerant_match import resolve
from agents.agent_a_retrieval.vocabulary import VOCABULARY


def _index():
    return KGramIndex(VOCABULARY)


def test_clean_query_resolves_via_exact_stage():
    results = resolve("toluene", VOCABULARY, _index())
    assert results[0].term == "toluene"
    assert results[0].stage == "exact"


def test_one_typo_resolves_via_edit_distance_stage():
    results = resolve("tolune", VOCABULARY, _index())
    assert results[0].term == "toluene"
    assert results[0].stage == "edit_distance"
    assert results[0].distance == 1


def test_two_typos_resolves_via_edit_distance_stage():
    results = resolve("tolueen", VOCABULARY, _index())  # transposition, distance 2
    terms = [r.term for r in results]
    assert "toluene" in terms


def test_case_and_whitespace_insensitive_exact_match():
    results = resolve("  TOLUENE  ", VOCABULARY, _index())
    assert results[0].term == "toluene"
    assert results[0].stage == "exact"


def test_unresolvable_query_returns_no_candidates():
    results = resolve("zzzqqqxxx", VOCABULARY, _index())
    # Nothing in the vocabulary shares k-grams or a Soundex code with this --
    # the cascade should return no candidates rather than guessing.
    assert results == []
