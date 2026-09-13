"""Hand-built inverted index for SDS document retrieval (M1, Lab 03).

A classic inverted index: maps each term to a list of postings, where each
posting records the document and the term's frequency in that document.

Supports Boolean queries (AND, OR, NOT) — the foundation of all retrieval
in this system.  M2's Agent A builds on top of this with TF-IDF scoring.

WHY HAND-BUILT (not sklearn or whoosh)?
    The project plan (§4) and CLAUDE.md explicitly state: the inverted index
    IS the Lab 03 deliverable.  Using a library would demonstrate nothing
    from the syllabus.  The viva will ask "how does your inverted index work?"
    and the answer must be "I built it, here's the data structure."
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Posting:
    """A single entry in a term's postings list.

    Attributes:
        doc_id: Unique document identifier (from SDSMetadata.document_id).
        term_frequency: Number of times the term appears in this document.
    """

    doc_id: str
    term_frequency: int = 1


class InvertedIndex:
    """Classic inverted index mapping terms to postings lists.

    Supports:
        - Adding documents (building the index).
        - Single-term lookup.
        - Boolean AND / OR / NOT queries.
        - Document frequency and collection statistics for TF-IDF (used by M2).

    Example:
        >>> idx = InvertedIndex()
        >>> idx.add_document("doc1", ["store", "below", "25", "toluene"])
        >>> idx.add_document("doc2", ["store", "above", "5", "acetone"])
        >>> idx.search("store")
        [Posting(doc_id='doc1', term_frequency=1), Posting(doc_id='doc2', term_frequency=1)]
        >>> idx.boolean_and("store", "toluene")
        ['doc1']
    """

    def __init__(self) -> None:
        # term → list of Posting, sorted by doc_id for efficient merging.
        self._index: dict[str, list[Posting]] = {}
        # All known document IDs (for NOT queries and IDF computation).
        self._all_doc_ids: set[str] = set()
        # doc_id → total token count (for normalisation in TF-IDF).
        self._doc_lengths: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Building the index
    # ------------------------------------------------------------------

    def add_document(self, doc_id: str, tokens: list[str]) -> None:
        """Add a document's tokens to the index.

        Counts term frequency and appends to the postings list.  If the
        same doc_id is added twice, postings accumulate (idempotent rebuild
        requires clearing first).

        Args:
            doc_id: Unique document identifier.
            tokens: Preprocessed tokens for this document.
        """
        self._all_doc_ids.add(doc_id)
        self._doc_lengths[doc_id] = len(tokens)

        # Count term frequencies in this document.
        tf: dict[str, int] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1

        # Append postings.
        for term, freq in tf.items():
            if term not in self._index:
                self._index[term] = []
            self._index[term].append(Posting(doc_id=doc_id, term_frequency=freq))

    # ------------------------------------------------------------------
    # Single-term retrieval
    # ------------------------------------------------------------------

    def search(self, term: str) -> list[Posting]:
        """Return the postings list for a term.

        Args:
            term: Preprocessed search term (must match the preprocessing
                  applied to documents).

        Returns:
            List of Posting objects, or empty list if term is not indexed.
        """
        return self._index.get(term, [])

    def doc_ids_for_term(self, term: str) -> set[str]:
        """Return the set of doc_ids containing a term.

        Convenience method for Boolean operations.
        """
        return {p.doc_id for p in self.search(term)}

    # ------------------------------------------------------------------
    # Boolean queries (Lab 03)
    # ------------------------------------------------------------------

    def boolean_and(self, term1: str, term2: str) -> list[str]:
        """Return doc_ids containing BOTH terms (intersection).

        Args:
            term1: First search term.
            term2: Second search term.

        Returns:
            Sorted list of doc_ids in the intersection.
        """
        set1 = self.doc_ids_for_term(term1)
        set2 = self.doc_ids_for_term(term2)
        return sorted(set1 & set2)

    def boolean_or(self, term1: str, term2: str) -> list[str]:
        """Return doc_ids containing EITHER term (union).

        Args:
            term1: First search term.
            term2: Second search term.

        Returns:
            Sorted list of doc_ids in the union.
        """
        set1 = self.doc_ids_for_term(term1)
        set2 = self.doc_ids_for_term(term2)
        return sorted(set1 | set2)

    def boolean_not(self, term: str) -> list[str]:
        """Return doc_ids that do NOT contain the term (complement).

        Args:
            term: Term to exclude.

        Returns:
            Sorted list of doc_ids not containing the term.
        """
        term_docs = self.doc_ids_for_term(term)
        return sorted(self._all_doc_ids - term_docs)

    def boolean_query(self, terms: list[str], operator: str = "AND") -> list[str]:
        """Execute a multi-term Boolean query.

        Args:
            terms: List of preprocessed search terms.
            operator: "AND" or "OR".

        Returns:
            Sorted list of matching doc_ids.
        """
        if not terms:
            return []

        result = self.doc_ids_for_term(terms[0])
        for term in terms[1:]:
            other = self.doc_ids_for_term(term)
            if operator.upper() == "AND":
                result = result & other
            else:
                result = result | other

        return sorted(result)

    # ------------------------------------------------------------------
    # Statistics for TF-IDF (used by M2)
    # ------------------------------------------------------------------

    def document_frequency(self, term: str) -> int:
        """Number of documents containing the term."""
        return len(self._index.get(term, []))

    def inverse_document_frequency(self, term: str) -> float:
        """IDF = log(N / df), where N = total docs, df = docs with term.

        Uses log base 10 to match sklearn's default TfidfVectorizer.
        Returns 0 if term is not in the index.
        """
        df = self.document_frequency(term)
        if df == 0:
            return 0.0
        n = len(self._all_doc_ids)
        return math.log10(n / df)

    @property
    def vocabulary(self) -> set[str]:
        """All unique terms in the index."""
        return set(self._index.keys())

    @property
    def num_documents(self) -> int:
        """Total number of documents indexed."""
        return len(self._all_doc_ids)

    @property
    def all_doc_ids(self) -> set[str]:
        """All document IDs in the index."""
        return self._all_doc_ids.copy()

    def get_doc_length(self, doc_id: str) -> int:
        """Total token count for a document (for length normalisation)."""
        return self._doc_lengths.get(doc_id, 0)

    def get_term_frequency(self, term: str, doc_id: str) -> int:
        """Term frequency for a specific term in a specific document."""
        for posting in self.search(term):
            if posting.doc_id == doc_id:
                return posting.term_frequency
        return 0

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise the index to a JSON-compatible dict."""
        return {
            "index": {
                term: [{"doc_id": p.doc_id, "tf": p.term_frequency} for p in postings]
                for term, postings in self._index.items()
            },
            "all_doc_ids": sorted(self._all_doc_ids),
            "doc_lengths": self._doc_lengths,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InvertedIndex":
        """Deserialise an index from a dict (loaded from JSON)."""
        idx = cls()
        idx._all_doc_ids = set(data.get("all_doc_ids", []))
        idx._doc_lengths = data.get("doc_lengths", {})
        for term, postings in data.get("index", {}).items():
            idx._index[term] = [
                Posting(doc_id=p["doc_id"], term_frequency=p["tf"]) for p in postings
            ]
        return idx
