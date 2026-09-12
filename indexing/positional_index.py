"""Hand-built positional index for phrase and proximity queries (M1, Lab 03).

Extends the inverted index by recording the POSITION of each term occurrence
within a document.  This enables:
    - Phrase queries:     "store below" must appear as an exact phrase.
    - Proximity queries:  "temperature" within 5 words of "storage".

WHY POSITIONAL?
    A plain inverted index knows that both "store" and "below" appear in a
    document, but not whether they're adjacent.  In SDS documents, "store
    below 25 °C" is a meaningful instruction — the words must be together.
    Without positional data, "below average store" would also match.

Data structure:
    term → { doc_id → [pos0, pos1, pos2, ...] }
    Positions are 0-indexed within each document's token list.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PositionalPosting:
    """A posting with position information.

    Attributes:
        doc_id: Document identifier.
        positions: Sorted list of 0-indexed positions where the term appears.
    """

    doc_id: str
    positions: list[int]

    @property
    def term_frequency(self) -> int:
        """TF = number of positions = number of occurrences."""
        return len(self.positions)


class PositionalIndex:
    """Positional index for phrase and proximity queries.

    Example:
        >>> pidx = PositionalIndex()
        >>> pidx.add_document("doc1", ["store", "below", "25", "toluene"])
        >>> pidx.phrase_query(["store", "below"])
        ['doc1']
        >>> pidx.proximity_query("store", "toluene", max_distance=5)
        ['doc1']
    """

    def __init__(self) -> None:
        # term → { doc_id → [positions] }
        self._index: dict[str, dict[str, list[int]]] = {}
        self._all_doc_ids: set[str] = set()

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def add_document(self, doc_id: str, tokens: list[str]) -> None:
        """Add a document's tokens with their positions.

        Args:
            doc_id: Unique document identifier.
            tokens: Preprocessed tokens, in order.
        """
        self._all_doc_ids.add(doc_id)

        for position, token in enumerate(tokens):
            if token not in self._index:
                self._index[token] = {}
            if doc_id not in self._index[token]:
                self._index[token][doc_id] = []
            self._index[token][doc_id].append(position)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_postings(self, term: str) -> list[PositionalPosting]:
        """Return positional postings for a term.

        Args:
            term: Preprocessed search term.

        Returns:
            List of PositionalPosting, one per document containing the term.
        """
        term_data = self._index.get(term, {})
        return [
            PositionalPosting(doc_id=doc_id, positions=sorted(positions))
            for doc_id, positions in term_data.items()
        ]

    def get_positions(self, term: str, doc_id: str) -> list[int]:
        """Return positions of a term in a specific document.

        Args:
            term: Preprocessed search term.
            doc_id: Document to check.

        Returns:
            Sorted list of positions, or empty list.
        """
        return sorted(self._index.get(term, {}).get(doc_id, []))

    # ------------------------------------------------------------------
    # Phrase queries (Lab 03)
    # ------------------------------------------------------------------

    def phrase_query(self, terms: list[str]) -> list[str]:
        """Find documents containing the exact phrase (terms in sequence).

        Algorithm:
            1. Find documents containing ALL terms (intersection).
            2. For each candidate document, check if the terms appear at
               consecutive positions (pos, pos+1, pos+2, ...).

        Args:
            terms: Ordered list of preprocessed terms forming the phrase.

        Returns:
            Sorted list of doc_ids containing the exact phrase.

        Example:
            >>> pidx.phrase_query(["store", "below"])
            ['doc1']  # only if "store" is immediately followed by "below"
        """
        if not terms:
            return []
        if len(terms) == 1:
            return sorted(self._index.get(terms[0], {}).keys())

        # Step 1: Find candidate documents (contain ALL terms).
        candidate_docs: set[str] | None = None
        for term in terms:
            term_docs = set(self._index.get(term, {}).keys())
            if candidate_docs is None:
                candidate_docs = term_docs
            else:
                candidate_docs &= term_docs

        if not candidate_docs:
            return []

        # Step 2: Check positional adjacency in each candidate.
        result: list[str] = []
        for doc_id in sorted(candidate_docs):
            # Get positions of the first term.
            first_positions = self.get_positions(terms[0], doc_id)

            for start_pos in first_positions:
                # Check if terms[1], terms[2], ... appear at start_pos+1, start_pos+2, ...
                found = True
                for offset, term in enumerate(terms[1:], start=1):
                    expected_pos = start_pos + offset
                    term_positions = self.get_positions(term, doc_id)
                    if expected_pos not in term_positions:
                        found = False
                        break
                if found:
                    result.append(doc_id)
                    break  # One match per document is enough.

        return result

    # ------------------------------------------------------------------
    # Proximity queries
    # ------------------------------------------------------------------

    def proximity_query(
        self, term1: str, term2: str, max_distance: int = 5
    ) -> list[str]:
        """Find documents where term1 and term2 appear within max_distance words.

        Args:
            term1: First search term.
            term2: Second search term.
            max_distance: Maximum word distance (inclusive).

        Returns:
            Sorted list of doc_ids where the terms are within range.

        Example:
            >>> pidx.proximity_query("temperature", "storage", max_distance=3)
            ['doc1']  # if "temperature" is within 3 words of "storage"
        """
        docs1 = set(self._index.get(term1, {}).keys())
        docs2 = set(self._index.get(term2, {}).keys())
        candidate_docs = docs1 & docs2

        result: list[str] = []
        for doc_id in sorted(candidate_docs):
            positions1 = self.get_positions(term1, doc_id)
            positions2 = self.get_positions(term2, doc_id)

            # Two-pointer merge to find any pair within max_distance.
            i, j = 0, 0
            found = False
            while i < len(positions1) and j < len(positions2) and not found:
                distance = abs(positions1[i] - positions2[j])
                if distance <= max_distance:
                    found = True
                elif positions1[i] < positions2[j]:
                    i += 1
                else:
                    j += 1

            if found:
                result.append(doc_id)

        return result

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise the index to a JSON-compatible dict."""
        return {
            "index": self._index,
            "all_doc_ids": sorted(self._all_doc_ids),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PositionalIndex":
        """Deserialise a positional index from a dict."""
        pidx = cls()
        pidx._all_doc_ids = set(data.get("all_doc_ids", []))
        pidx._index = data.get("index", {})
        return pidx
