"""Unit tests for the hand-built KGramIndex lookup (Lab 04).

Problem this solves:
Validates k-gram decomposition with boundary markers ($), overlap-based candidate
retrieval for misspelled chemical names, and incremental term addition.

Why this technique:
Direct tests of character n-gram mapping and overlap candidate ranking per Lab 04 requirements.
"""

from agents.agent_a_retrieval.kgram_index import KGramIndex, get_kgrams


def test_kgram_generation_with_boundary_markers():
    """Verify get_kgrams generates trigrams with '$' boundary padding."""
    grams = get_kgrams("toluene", k=3)
    # "$toluene$" -> $to, tol, olu, lue, uen, ene, ne$
    expected = {"$to", "tol", "olu", "lue", "uen", "ene", "ne$"}
    assert grams == expected


def test_kgram_candidates_ranking():
    """Verify k-gram overlap identifies and ranks candidate terms for misspelled input."""
    vocab = ["toluene", "acetone", "ethanol", "methanol"]
    kgram = KGramIndex(vocab, k=3)

    # "tolune" shares almost all k-grams with "toluene"
    candidates = kgram.candidates("tolune", min_overlap=1)
    assert len(candidates) > 0
    assert candidates[0] == "toluene"


def test_kgram_add_term_incremental():
    """Verify add_term adds a new term and its k-grams dynamically."""
    kgram = KGramIndex(["toluene"], k=3)
    assert "acetone" not in kgram.vocabulary

    kgram.add_term("acetone")
    assert "acetone" in kgram.vocabulary
    candidates = kgram.candidates("acetne", min_overlap=1)
    assert "acetone" in candidates
