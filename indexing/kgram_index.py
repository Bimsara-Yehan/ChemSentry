"""Hand-built k-gram index for tolerant retrieval (M1, Lab 04).

A k-gram index maps character-level n-grams to the terms containing them.
This enables:
    - Wildcard queries:  *chlorate → {"chlorate", "perchlorate", "potassium chlorate"}
    - Fuzzy matching:    candidates sharing k-grams with a misspelled query term

WHY K-GRAMS FOR CHEMISTRY?
    Chemical names are suffix-structured (plan §5.3):
        -ate   → chlorate, sulfate, nitrate, perchlorate
        -ide   → chloride, sulfide, oxide, hydroxide
        -ol    → methanol, ethanol, propanol
        -ene   → toluene, benzene, styrene
    A single wildcard query like *chlorate efficiently retrieves an entire
    chemical family.  This is our differentiator — same Lab 04 technique,
    domain-specific impact.

IMPORTANT FRAMING (plan §5.3):
    Wildcard matching is a RETRIEVAL mechanism, not a classifier.
    "*chlorate" retrieves candidates; hazard class comes from authoritative
    metadata (SDS, CAMEO), never inferred from the suffix.
"""

from __future__ import annotations


class KGramIndex:
    """K-gram index for wildcard and fuzzy term matching.

    Builds an index of character-level k-grams (default k=3, i.e. trigrams)
    from a vocabulary of terms.  Each k-gram points to the set of terms
    containing it.

    Terms are padded with '$' markers at start and end so that prefix and
    suffix grams are distinct from interior grams:
        "toluene" → "$to", "tol", "olu", "lue", "uen", "ene", "ne$"

    Example:
        >>> kgram = KGramIndex(k=3)
        >>> kgram.build({"chlorate", "perchlorate", "chloride", "toluene"})
        >>> kgram.wildcard_query("*chlorate")
        {'chlorate', 'perchlorate'}
        >>> kgram.candidates_for("tolune")  # misspelling of toluene
        {'toluene'}
    """

    def __init__(self, k: int = 3) -> None:
        """
        Args:
            k: Length of each character n-gram. Default 3 (trigrams).
        """
        self._k = k
        # k-gram → set of terms containing that k-gram.
        self._index: dict[str, set[str]] = {}
        # All terms in the vocabulary.
        self._vocabulary: set[str] = set()

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def _generate_kgrams(self, term: str) -> list[str]:
        """Generate k-grams for a term, with $ padding.

        Args:
            term: The term to decompose.

        Returns:
            List of k-gram strings.

        Example (k=3):
            >>> self._generate_kgrams("toluene")
            ['$to', 'tol', 'olu', 'lue', 'uen', 'ene', 'ne$']
        """
        padded = f"${term}$"
        return [padded[i : i + self._k] for i in range(len(padded) - self._k + 1)]

    def build(self, vocabulary: set[str]) -> None:
        """Build the k-gram index from a vocabulary of terms.

        Args:
            vocabulary: Set of terms (typically from the inverted index vocabulary).
        """
        self._vocabulary = vocabulary.copy()
        self._index.clear()

        for term in vocabulary:
            for kgram in self._generate_kgrams(term):
                if kgram not in self._index:
                    self._index[kgram] = set()
                self._index[kgram].add(term)

    def add_term(self, term: str) -> None:
        """Add a single term to the existing index.

        Args:
            term: New term to index.
        """
        self._vocabulary.add(term)
        for kgram in self._generate_kgrams(term):
            if kgram not in self._index:
                self._index[kgram] = set()
            self._index[kgram].add(term)

    # ------------------------------------------------------------------
    # Wildcard queries (Lab 04)
    # ------------------------------------------------------------------

    def wildcard_query(self, pattern: str) -> set[str]:
        """Find terms matching a wildcard pattern.

        Supports:
            *suffix    → terms ending with suffix (e.g. *chlorate)
            prefix*    → terms starting with prefix (e.g. methyl*)
            pre*suf    → terms starting with pre and ending with suf

        Algorithm:
            1. Split pattern on '*' to get fixed parts.
            2. Generate k-grams for each fixed part.
            3. Intersect the candidate sets from each k-gram.
            4. Post-filter candidates to ensure they actually match the pattern.

        Args:
            pattern: Wildcard pattern (e.g. "*chlorate", "methyl*", "*prop*").

        Returns:
            Set of matching terms from the vocabulary.

        Example:
            >>> kgram.wildcard_query("*chlorate")
            {'chlorate', 'perchlorate'}
        """
        if "*" not in pattern:
            # No wildcard — exact match.
            return {pattern} if pattern in self._vocabulary else set()

        # Split pattern into fixed parts.
        parts = [p for p in pattern.split("*") if p]

        if not parts:
            # Pattern is just "*" — return everything.
            return self._vocabulary.copy()

        # Generate k-grams for each fixed part and intersect candidates.
        candidates: set[str] | None = None

        for part in parts:
            # Add padding for prefix/suffix awareness.
            if pattern.startswith(part):
                # This part is a prefix.
                padded_part = f"${part}"
            elif pattern.endswith(part):
                # This part is a suffix.
                padded_part = f"{part}$"
            else:
                padded_part = part

            # Generate k-grams for this part.
            part_kgrams = self._generate_kgrams_from_substring(padded_part)

            # Intersect candidate sets.
            for kgram in part_kgrams:
                kgram_matches = self._index.get(kgram, set())
                if candidates is None:
                    candidates = kgram_matches.copy()
                else:
                    candidates &= kgram_matches

            if candidates is not None and not candidates:
                return set()  # No candidates survive — early exit.

        if candidates is None:
            return set()

        # Post-filter: k-gram intersection gives candidates, but we must
        # verify they actually match the original pattern.
        return {term for term in candidates if self._matches_pattern(term, pattern)}

    def _generate_kgrams_from_substring(self, substring: str) -> list[str]:
        """Generate k-grams from a (possibly padded) substring.

        Unlike _generate_kgrams, this doesn't add its own $ padding — the
        caller handles that for prefix/suffix awareness.
        """
        if len(substring) < self._k:
            return [substring] if substring else []
        return [
            substring[i : i + self._k]
            for i in range(len(substring) - self._k + 1)
        ]

    @staticmethod
    def _matches_pattern(term: str, pattern: str) -> bool:
        """Check if a term matches a wildcard pattern exactly.

        Simple glob-style matching: '*' matches any sequence of characters.

        Args:
            term: Term to check.
            pattern: Pattern with '*' wildcards.

        Returns:
            True if the term matches the pattern.
        """
        parts = pattern.split("*")

        # Check prefix.
        if parts[0] and not term.startswith(parts[0]):
            return False

        # Check suffix.
        if parts[-1] and not term.endswith(parts[-1]):
            return False

        # Check interior parts appear in order.
        pos = 0
        for part in parts:
            if not part:
                continue
            idx = term.find(part, pos)
            if idx == -1:
                return False
            pos = idx + len(part)

        return True

    # ------------------------------------------------------------------
    # Fuzzy matching (candidates for misspelled terms)
    # ------------------------------------------------------------------

    def candidates_for(self, term: str, min_shared_ratio: float = 0.5) -> set[str]:
        """Find vocabulary terms that share enough k-grams with the given term.

        This is the first step in tolerant retrieval (Lab 04): generate
        candidates, then M2 applies Levenshtein distance to rank them.

        Args:
            term: Possibly misspelled input term.
            min_shared_ratio: Minimum fraction of the term's k-grams that
                a candidate must share (Jaccard-like threshold).

        Returns:
            Set of candidate terms from the vocabulary.
        """
        term_kgrams = set(self._generate_kgrams(term))

        if not term_kgrams:
            return set()

        # Count how many of the term's k-grams each vocabulary term shares.
        candidate_scores: dict[str, int] = {}
        for kgram in term_kgrams:
            for vocab_term in self._index.get(kgram, set()):
                candidate_scores[vocab_term] = candidate_scores.get(vocab_term, 0) + 1

        # Filter by minimum shared ratio.
        threshold = len(term_kgrams) * min_shared_ratio
        return {
            vocab_term
            for vocab_term, shared_count in candidate_scores.items()
            if shared_count >= threshold
        }

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def vocabulary(self) -> set[str]:
        """All terms in the index."""
        return self._vocabulary.copy()

    @property
    def k(self) -> int:
        """The k-gram size."""
        return self._k

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise the index to a JSON-compatible dict."""
        return {
            "k": self._k,
            "vocabulary": sorted(self._vocabulary),
            "index": {
                kgram: sorted(terms) for kgram, terms in self._index.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KGramIndex":
        """Deserialise a k-gram index from a dict."""
        kgram = cls(k=data.get("k", 3))
        kgram._vocabulary = set(data.get("vocabulary", []))
        kgram._index = {
            kg: set(terms) for kg, terms in data.get("index", {}).items()
        }
        return kgram
