"""Hand-built k-gram index for tolerant chemical-name matching (Lab 04).

A k-gram index maps each k-length character n-gram to the vocabulary terms that
contain it. Given a misspelled query, its k-grams overlap heavily with the k-grams of
the *intended* term even when several characters are wrong -- so intersecting
candidate sets by shared k-grams narrows the field to a handful of plausible terms
before the more expensive edit-distance comparison runs. Built by hand (no library)
per Lab 04 and CLAUDE.md's classical-IR constraint: this is the deliverable, not a
black box.
"""

from collections import defaultdict

DEFAULT_K = 3
BOUNDARY = "$"


def get_kgrams(term: str, k: int = DEFAULT_K) -> set[str]:
    """Return the set of k-grams for `term`, padded with boundary markers.

    Padding (e.g. "$to", "tol", ..., "ne$") lets the index distinguish a term that
    starts/ends with a given substring from one that merely contains it in the
    middle -- the same trick Lab 04 uses for prefix/suffix wildcard queries.
    """
    padded = f"{BOUNDARY}{term.lower()}{BOUNDARY}"
    if len(padded) < k:
        return {padded}
    return {padded[i : i + k] for i in range(len(padded) - k + 1)}


class KGramIndex:
    """Maps k-grams to the vocabulary terms containing them.

    Supports narrowing an arbitrary (possibly misspelled) query down to a small
    candidate set via k-gram overlap, which is what makes running Levenshtein edit
    distance against the *whole* vocabulary on every query unnecessary.
    """

    def __init__(self, vocabulary: list[str], k: int = DEFAULT_K) -> None:
        self.k = k
        self.vocabulary = list(vocabulary)
        self._index: dict[str, set[str]] = defaultdict(set)
        for term in self.vocabulary:
            for gram in get_kgrams(term, k):
                self._index[gram].add(term)

    def candidates(self, query: str, min_overlap: int = 1) -> list[str]:
        """Return vocabulary terms sharing at least `min_overlap` k-grams with `query`.

        A low `min_overlap` favours recall (catches heavily misspelled queries) at
        the cost of a larger candidate set for the edit-distance stage to rank; the
        cascade in tolerant_match.py tunes this trade-off.
        """
        query_grams = get_kgrams(query, self.k)
        overlap_counts: dict[str, int] = defaultdict(int)
        for gram in query_grams:
            for term in self._index.get(gram, ()):
                overlap_counts[term] += 1
        return [
            term
            for term, count in sorted(
                overlap_counts.items(), key=lambda item: item[1], reverse=True
            )
            if count >= min_overlap
        ]
