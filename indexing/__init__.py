"""Inverted, positional, and k-gram indexes (M1/M2, Labs 03-04).

Public API:
    build_all_indexes(documents)     — build all three indexes from documents
    add_document_to_indexes(...)     — add a single doc to existing indexes
    save_indexes(directory, ...)     — persist to JSON
    load_indexes(directory)          — load from JSON
    indexes_exist(directory)         — check if saved indexes exist

Index classes:
    InvertedIndex   — Boolean retrieval + TF-IDF stats (Lab 03)
    PositionalIndex — Phrase and proximity queries (Lab 03)
    KGramIndex      — Wildcard and fuzzy matching (Lab 04)
"""

from indexing.index_builder import add_document_to_indexes, build_all_indexes
from indexing.inverted_index import InvertedIndex, Posting
from indexing.kgram_index import KGramIndex
from indexing.persistence import indexes_exist, load_indexes, save_indexes
from indexing.positional_index import PositionalIndex, PositionalPosting

__all__ = [
    "build_all_indexes",
    "add_document_to_indexes",
    "save_indexes",
    "load_indexes",
    "indexes_exist",
    "InvertedIndex",
    "Posting",
    "PositionalIndex",
    "PositionalPosting",
    "KGramIndex",
]
