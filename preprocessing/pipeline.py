"""Full preprocessing pipeline for SDS documents (M1, Lab 02).

Composes the three preprocessing stages in order:
    1. Tokenize  — chemistry-aware splitting with identifier protection
    2. Stop words — removal with negation preservation
    3. Stem       — selective stemming with chemical suffix protection

This is the single entry point that the extraction pipeline and the indexing
layer call.  Keeping it in one place ensures that both documents and queries
go through the exact same pipeline — a core Lab 02 requirement.

Usage:
    from preprocessing.pipeline import preprocess
    tokens = preprocess("Store below 25 °C. CAS: 78-93-3. Do NOT mix with acids.")
"""

from __future__ import annotations

from preprocessing.tokenizer import tokenize
from preprocessing.stopwords import remove_stopwords
from preprocessing.stemmer import selective_stem


def preprocess(text: str) -> list[str]:
    """Run the full preprocessing pipeline on raw text.

    Args:
        text: Raw SDS text (a section or full document).

    Returns:
        List of preprocessed tokens — lowercase, stop-word-free, selectively
        stemmed, with chemical identifiers intact.

    Example:
        >>> preprocess("Do NOT store near strong oxidisers. CAS: 78-93-3.")
        ['not', 'store', 'near', 'strong', 'oxidis', '78-93-3']
    """
    tokens = tokenize(text)
    tokens = remove_stopwords(tokens)
    tokens = selective_stem(tokens)
    return tokens


def preprocess_query(query: str) -> list[str]:
    """Preprocess a user query using the same pipeline as documents.

    Lab 02's core invariant: documents and queries must go through the
    same preprocessing.  This function exists as a named alias to make
    that explicit in calling code.

    Args:
        query: Raw user query string.

    Returns:
        Preprocessed query tokens.
    """
    return preprocess(query)
