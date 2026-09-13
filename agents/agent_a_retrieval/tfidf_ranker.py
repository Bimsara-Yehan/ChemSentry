"""TF-IDF cosine ranking over retrieved SDS passages (M2, Lab 05).

Boolean/positional retrieval (Lab 03, `indexing/`) answers "which documents
contain these terms" -- it has no notion of *how well* a passage answers the
query. This module ranks a candidate set of passages by TF-IDF cosine
similarity, the answer to "which passage actually answers the question."

Why sklearn here and not hand-built, unlike the inverted/positional/k-gram
indexes in `indexing/`: Lab 05 explicitly introduces `TfidfVectorizer` as the
taught technique -- the hand-built deliverable is Lab 03/04's index
structures, not TF-IDF itself. Re-implementing TF-IDF by hand would
demonstrate the same lab twice for no pedagogical gain.

Why this reuses `preprocessing.pipeline.preprocess` instead of sklearn's
built-in tokenizer: Lab 02's invariant -- documents and queries must be
tokenized identically -- is a named hard requirement (CLAUDE.md, plan §27).
Letting sklearn tokenize independently would silently violate it (e.g.
"2-butanone" would fragment under sklearn's default token pattern even
though `preprocessing/tokenizer.py` protects it). Passing already-tokenized
lists via `tokenizer`/`preprocessor` overrides is the standard way to bolt a
custom tokenizer onto `TfidfVectorizer`.
"""

from __future__ import annotations

from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from preprocessing.pipeline import preprocess, preprocess_query


@dataclass
class RankedPassage:
    """One ranked result: which passage, and how well it matched the query."""

    unit_id: str
    score: float


class TfidfRanker:
    """Ranks text passages against a query using TF-IDF + cosine similarity.

    A "passage" is deliberately left up to the caller -- it can be a whole
    document (`unit_id = document_id`) or a single GHS section
    (`unit_id = f"{document_id}#section{n}"`), matching how Agent A's
    retrieval cascade narrows a candidate set before ranking it (plan §11):
    Boolean/positional retrieval finds candidate passages, this ranks them.
    """

    def __init__(self, passages: dict[str, str]) -> None:
        """Build the TF-IDF matrix from a corpus of passages.

        Args:
            passages: unit_id -> raw text. Preprocessed internally with the
                same pipeline `preprocess_query` uses, so a query and the
                corpus it's ranked against are guaranteed to share a tokenizer.
        """
        self._unit_ids = list(passages.keys())
        token_lists = [preprocess(passages[unit_id]) for unit_id in self._unit_ids]

        self._vectorizer = TfidfVectorizer(
            preprocessor=lambda tokens: tokens,
            tokenizer=lambda tokens: tokens,
            token_pattern=None,
            lowercase=False,  # already lowercased by preprocessing.tokenizer
        )
        self._matrix = self._vectorizer.fit_transform(token_lists)

    def rank(self, query: str, top_k: int = 5) -> list[RankedPassage]:
        """Rank all passages by cosine similarity to `query`.

        Args:
            query: Raw user/agent query text.
            top_k: Maximum number of results to return.

        Returns:
            RankedPassage list, highest score first, zero-score passages
            excluded (a zero score means the query and passage share no
            indexed terms at all -- not a meaningful ranking signal).
        """
        query_tokens = preprocess_query(query)
        query_vector = self._vectorizer.transform([query_tokens])
        scores = cosine_similarity(query_vector, self._matrix)[0]

        ranked = sorted(
            zip(self._unit_ids, scores), key=lambda pair: pair[1], reverse=True
        )
        return [
            RankedPassage(unit_id=unit_id, score=float(score))
            for unit_id, score in ranked[:top_k]
            if score > 0
        ]
