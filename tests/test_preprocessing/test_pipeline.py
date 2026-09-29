"""Unit tests for the end-to-end preprocessing pipeline (M1, Lab 02).

Problem this solves:
Verifies that text tokenization, stop-word removal, and selective stemming integrate
harmoniously for full document passages and search queries.

Why this technique:
End-to-end integration tests on both preprocess() (documents) and preprocess_query()
guarantee consistency between indexed documents and user queries.
"""

from preprocessing.pipeline import preprocess, preprocess_query


def test_full_document_preprocessing_protects_identifiers_and_stems_instructions():
    """Verify that document preprocessing preserves chemical identifiers while stemming verbs."""
    text = (
        "Store toluene CAS 108-88-3 in tightly closed containers below 25 °C. "
        "Do not store with sodium chlorate or sulfuric acid."
    )
    tokens = preprocess(text)

    # Identifiers survive
    assert "108-88-3" in tokens
    assert "toluene" in tokens
    assert "chlorate" in tokens

    # Stop words removed ("in", "with", "or")
    assert "in" not in tokens
    assert "with" not in tokens
    assert "or" not in tokens

    # Verbs stemmed ("containers" -> "contain", "store" / "storing")
    assert "contain" in tokens or "container" in tokens


def test_query_preprocessing_matches_document_token_stream():
    """Verify that query preprocessing produces tokens aligned with document preprocessing."""
    query = "storing toluene CAS 108-88-3 safely"
    query_tokens = preprocess_query(query)

    assert "108-88-3" in query_tokens
    assert "toluene" in query_tokens
    assert "store" in query_tokens
