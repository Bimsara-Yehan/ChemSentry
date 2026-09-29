"""Inverted, positional, and k-gram indexes (M1/M2, Labs 03-04).

Public API:
    build_all_indexes(documents)     — build all three indexes from documents
    add_document_to_indexes(...)     — add a single doc to existing indexes

Index classes:
    InvertedIndex   — Boolean retrieval + TF-IDF stats (Lab 03)
    PositionalIndex — Phrase and proximity queries (Lab 03)
    KGramIndex      — Tolerant matching and candidate retrieval (Lab 04)
"""

from agents.agent_a_retrieval.kgram_index import KGramIndex
from indexing.index_builder import add_document_to_indexes, build_all_indexes
from indexing.inverted_index import InvertedIndex, Posting
from indexing.positional_index import PositionalIndex, PositionalPosting

__all__ = [
    "build_all_indexes",
    "add_document_to_indexes",
    "InvertedIndex",
    "Posting",
    "PositionalIndex",
    "PositionalPosting",
    "KGramIndex",
]
