"""Unit tests for the hand-built PositionalIndex (M1, Lab 03).

Problem this solves:
Validates positional posting lists, exact phrase lookups, and proximity distance matching
for phrases like "store below" where token adjacency and order are semantically critical.

Why this technique:
Direct tests on token offsets and positional merge algorithms per Lab 03 requirements.
"""

from indexing.positional_index import PositionalIndex, PositionalPosting


def test_positional_postings_record_exact_offsets():
    """Verify positional index records 0-indexed positions for term occurrences."""
    pidx = PositionalIndex()
    pidx.add_document("doc1", ["store", "in", "cool", "dry", "place", "store"])

    postings = pidx.get_postings("store")
    assert len(postings) == 1
    assert postings[0] == PositionalPosting(doc_id="doc1", positions=[0, 5])
    assert postings[0].term_frequency == 2


def test_phrase_query_exact_adjacency():
    """Verify phrase query matches adjacent terms in correct relative order."""
    pidx = PositionalIndex()
    # doc1 has exact phrase "store below 25"
    pidx.add_document("doc1", ["store", "below", "25", "celsius"])
    # doc2 has words out of order or separated
    pidx.add_document("doc2", ["below", "25", "store", "celsius"])
    # doc3 has terms separated by another word
    pidx.add_document("doc3", ["store", "strictly", "below", "25"])

    # Match 2-word phrase
    assert pidx.phrase_query(["store", "below"]) == ["doc1"]
    # Match 3-word phrase
    assert pidx.phrase_query(["store", "below", "25"]) == ["doc1"]
    # No match for non-existent phrase
    assert pidx.phrase_query(["below", "store"]) == []


def test_proximity_query_distance_threshold():
    """Verify proximity query matches words within max_distance tokens."""
    pidx = PositionalIndex()
    # "store" at pos 0, "toluene" at pos 3 -> distance = 3
    pidx.add_document("doc1", ["store", "in", "drum", "toluene"])
    # "store" at pos 0, "toluene" at pos 7 -> distance = 7
    pidx.add_document("doc2", ["store", "a", "b", "c", "d", "e", "toluene"])

    # Within distance 4: doc1 matches, doc2 does not
    assert pidx.proximity_query("store", "toluene", max_distance=4) == ["doc1"]
    # Within distance 8: both match
    assert sorted(pidx.proximity_query("store", "toluene", max_distance=8)) == [
        "doc1",
        "doc2",
    ]
