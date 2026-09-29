"""Unit tests for the hand-built InvertedIndex (M1, Lab 03).

Problem this solves:
Validates posting list construction, term frequency calculation, collection statistics,
and Boolean search operators (AND, OR, NOT) without external search libraries.

Why this technique:
Direct white-box tests on InvertedIndex data structures and algorithms matching Lab 03 requirements.
"""

from indexing.inverted_index import InvertedIndex, Posting


def test_inverted_index_postings_and_term_frequency():
    """Verify postings list records doc_id and exact term frequency."""
    index = InvertedIndex()
    index.add_document("doc1", ["toluene", "store", "toluene", "cool"])
    index.add_document("doc2", ["store", "acetone", "cool"])

    postings = index.search("toluene")
    assert len(postings) == 1
    assert postings[0] == Posting(doc_id="doc1", term_frequency=2)

    store_postings = index.search("store")
    assert len(store_postings) == 2
    assert store_postings[0].doc_id == "doc1"
    assert store_postings[1].doc_id == "doc2"


def test_boolean_and_query():
    """Verify boolean AND correctly intersects document posting sets."""
    index = InvertedIndex()
    index.add_document("doc1", ["toluene", "flammable", "liquid"])
    index.add_document("doc2", ["acetone", "flammable", "liquid"])
    index.add_document("doc3", ["sodium", "hydroxide", "solid"])

    # Both doc1 and doc2 have 'flammable' and 'liquid'
    assert sorted(index.boolean_and("flammable", "liquid")) == ["doc1", "doc2"]
    # Only doc1 has 'toluene' and 'flammable'
    assert index.boolean_and("toluene", "flammable") == ["doc1"]
    # No document has both 'toluene' and 'acetone'
    assert index.boolean_and("toluene", "acetone") == []


def test_boolean_or_query():
    """Verify boolean OR correctly unions document posting sets."""
    index = InvertedIndex()
    index.add_document("doc1", ["toluene"])
    index.add_document("doc2", ["acetone"])
    index.add_document("doc3", ["ethanol"])

    assert sorted(index.boolean_or("toluene", "acetone")) == ["doc1", "doc2"]


def test_boolean_not_query():
    """Verify boolean NOT computes complement relative to collection documents."""
    index = InvertedIndex()
    index.add_document("doc1", ["toluene", "flammable"])
    index.add_document("doc2", ["acetone", "flammable"])
    index.add_document("doc3", ["water", "nonflammable"])

    # Documents not containing 'flammable'
    assert index.boolean_not("flammable") == ["doc3"]


def test_multi_token_boolean_query():
    """Verify multi-token boolean query parsing and evaluation."""
    index = InvertedIndex()
    index.add_document("doc1", ["store", "below", "25", "toluene"])
    index.add_document("doc2", ["store", "above", "5", "acetone"])
    index.add_document("doc3", ["ventilate", "store", "toluene"])

    results = index.boolean_query(["store", "toluene"], operator="AND")
    assert sorted(results) == ["doc1", "doc3"]


def test_collection_statistics_for_tfidf():
    """Verify document frequency and length tracking used by M2 TF-IDF scoring."""
    index = InvertedIndex()
    index.add_document("doc1", ["a", "b", "c"])
    index.add_document("doc2", ["a", "d"])

    assert index.num_documents == 2
    assert index.document_frequency("a") == 2
    assert index.document_frequency("b") == 1
    assert index.get_doc_length("doc1") == 3
    assert index.get_doc_length("doc2") == 2
