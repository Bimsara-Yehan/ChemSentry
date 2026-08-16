"""Tests for the hand-built k-gram index (Lab 04)."""

from agents.agent_a_retrieval.kgram_index import KGramIndex, get_kgrams
from agents.agent_a_retrieval.vocabulary import VOCABULARY


def test_get_kgrams_includes_boundary_markers():
    grams = get_kgrams("toluene", k=3)
    assert "$to" in grams
    assert "ne$" in grams


def test_get_kgrams_short_term_produces_boundary_grams():
    # "ol" pads to "$ol$" (4 chars) -- still >= k, so it yields two grams, not one.
    grams = get_kgrams("ol", k=3)
    assert grams == {"$ol", "ol$"}


def test_get_kgrams_empty_term_returns_padded_string_unsplit():
    # Padding an empty term ("$$" , 2 chars) is shorter than k=3 -- too short to
    # slide a window over, so the whole padded string is returned as one gram.
    grams = get_kgrams("", k=3)
    assert grams == {"$$"}


def test_candidates_finds_exact_term_by_kgram_overlap():
    index = KGramIndex(VOCABULARY)
    candidates = index.candidates("toluene")
    assert "toluene" in candidates


def test_candidates_finds_misspelled_term():
    index = KGramIndex(VOCABULARY)
    candidates = index.candidates("tolune")
    assert "toluene" in candidates


def test_candidates_ranks_closer_terms_first():
    index = KGramIndex(VOCABULARY)
    candidates = index.candidates("acetne")
    assert candidates[0] == "acetone"
