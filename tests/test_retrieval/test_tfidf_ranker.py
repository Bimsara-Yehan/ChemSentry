"""Unit tests for agents/agent_a_retrieval/tfidf_ranker.py (M2, Lab 05)."""

from agents.agent_a_retrieval.tfidf_ranker import TfidfRanker


def _sample_passages() -> dict[str, str]:
    return {
        "toluene#section7": "Store below 25 C. Keep away from heat and ignition sources.",
        "acetone#section7": "Store below 20 C. Highly flammable, keep away from sparks.",
        "sodium_hydroxide#section10": (
            "Violent reactions possible with acids and metals. Corrosive."
        ),
    }


def test_rank_prefers_the_passage_that_actually_matches() -> None:
    """A storage-conditions query should rank the two storage passages above
    the unrelated reactivity passage -- TF-IDF only, so the query must share
    literal (post-stemming) vocabulary with the passages it's expected to
    match, not just a topic in the abstract."""
    ranker = TfidfRanker(_sample_passages())
    results = ranker.rank("store below heat ignition sparks", top_k=5)

    result_ids = [r.unit_id for r in results]
    assert "sodium_hydroxide#section10" not in result_ids
    assert "toluene#section7" in result_ids
    assert "acetone#section7" in result_ids


def test_rank_orders_by_relevance_not_insertion_order() -> None:
    """A query closely matching one passage's exact wording should rank it
    above a passage that only shares a couple of generic terms."""
    ranker = TfidfRanker(_sample_passages())
    results = ranker.rank("corrosive reactions with acids and metals", top_k=5)

    assert results[0].unit_id == "sodium_hydroxide#section10"


def test_rank_returns_empty_for_completely_unrelated_query() -> None:
    """A query sharing no indexed terms with any passage scores zero
    everywhere and should return no results, not a meaningless ranking."""
    ranker = TfidfRanker(_sample_passages())
    results = ranker.rank("zzzqqqxxx nonexistent gibberish", top_k=5)

    assert results == []


def test_rank_respects_top_k() -> None:
    ranker = TfidfRanker(_sample_passages())
    results = ranker.rank("store keep flammable", top_k=1)

    assert len(results) == 1


def test_query_and_documents_share_the_chemical_identifier_tokenizer() -> None:
    """Regression guard for the project's central Lab 02 invariant: a query
    containing a chemical identifier (a CAS-shaped number) must be tokenized
    the same way the corpus was, not fragmented by a default tokenizer."""
    passages = {
        "doc1": "CAS-No. : 78-93-3. Store below 25 C.",
        "doc2": "Some unrelated passage about packaging materials.",
    }
    ranker = TfidfRanker(passages)
    results = ranker.rank("78-93-3", top_k=5)

    assert len(results) == 1
    assert results[0].unit_id == "doc1"
