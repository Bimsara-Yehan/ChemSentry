"""Unit tests for agents/agent_a_retrieval/index_elimination.py (M2, Lab 06A)."""

from agents.agent_a_retrieval.index_elimination import (
    IndexEliminator,
    rank_with_elimination,
)
from indexing.inverted_index import InvertedIndex
from preprocessing.pipeline import preprocess


def _build_corpus() -> tuple[InvertedIndex, dict[str, list[str]], dict[str, str]]:
    raw_docs = {
        "toluene": "Toluene. Store below 25 C. Keep away from heat and ignition sources.",
        "acetone": "Acetone. Store below 20 C. Keep away from heat and ignition sources.",
        # Shares only "store" (common, low-IDF) with the two above -- neither
        # the rare term "toluene"/"acetone" nor "heat" -- so it should cover
        # a smaller fraction of a query that names one of those chemicals.
        "unrelated": "Store below heat. General warehouse packaging notice.",
    }
    index = InvertedIndex()
    doc_tokens: dict[str, list[str]] = {}
    for doc_id, text in raw_docs.items():
        tokens = preprocess(text)
        doc_tokens[doc_id] = tokens
        index.add_document(doc_id, tokens)
    return index, doc_tokens, raw_docs


def test_eliminate_selects_high_idf_term_over_common_terms() -> None:
    """ "toluene" is the rarest term (appears in 1/3 docs); "store"/"heat"
    appear in all three and should not, by themselves, pull in the
    unrelated document once the high-IDF term is what's selected."""
    index, doc_tokens, _ = _build_corpus()
    eliminator = IndexEliminator(index, doc_tokens)

    candidates = eliminator.eliminate("toluene", top_k_terms=1, overlap_threshold=0.0)

    assert candidates == {"toluene"}


def test_eliminate_overlap_filter_excludes_partial_coverage() -> None:
    """A query naming both "toluene" and "heat" is fully covered (2/2) by the
    toluene document but only half-covered (1/2, just "heat") by the
    unrelated document -- an overlap-coefficient threshold above 0.5
    separates a full match from a partial coincidental one, which a
    document-size-sensitive measure like plain Jaccard cannot do reliably
    (see module docstring: real-corpus Jaccard values collapse to ~0.001-0.004
    regardless of match quality once documents run to hundreds of tokens)."""
    index, doc_tokens, _ = _build_corpus()
    eliminator = IndexEliminator(index, doc_tokens)

    candidates = eliminator.eliminate(
        "toluene heat", top_k_terms=5, overlap_threshold=0.75
    )

    assert candidates == {"toluene"}
    assert "unrelated" not in candidates


def test_eliminate_returns_empty_for_query_with_no_indexed_terms() -> None:
    index, doc_tokens, _ = _build_corpus()
    eliminator = IndexEliminator(index, doc_tokens)

    assert eliminator.eliminate("zzzqqqxxx nonexistent") == set()


def test_rank_with_elimination_ranks_only_surviving_candidates() -> None:
    index, doc_tokens, raw_docs = _build_corpus()
    eliminator = IndexEliminator(index, doc_tokens)

    results = rank_with_elimination("toluene", eliminator, raw_docs, top_k=5)

    assert len(results) == 1
    assert results[0].unit_id == "toluene"


def test_rank_with_elimination_returns_empty_when_nothing_survives() -> None:
    index, doc_tokens, raw_docs = _build_corpus()
    eliminator = IndexEliminator(index, doc_tokens)

    results = rank_with_elimination("zzzqqqxxx", eliminator, raw_docs, top_k=5)

    assert results == []
