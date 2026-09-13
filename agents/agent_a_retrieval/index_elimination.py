"""Hand-built index elimination for the live-alert retrieval path (M2, Lab 06A).

A live safety alert can't wait on TF-IDF cosine ranking over the entire
corpus. This module trims the candidate set with two cheap heuristics
*before* the expensive ranking step ever runs, exactly as named in the plan
(plan §Part III item 4, "index elimination"):

    1. High-IDF term selection -- only the query's rarest (highest-IDF)
       terms are used to pull candidates from the inverted index. Common
       terms (low IDF) appear in nearly every document, so including them
       costs a postings-list union without narrowing anything down.
    2. Set-overlap pre-filter -- candidates surviving step 1 are further
       culled by how much of the *query* is covered by each candidate
       document, below a configurable threshold.

DIVERGENCE FROM THE PLAN'S "JACCARD-BASED FILTERING" WORDING, MEASURED NOT
GUESSED: plain Jaccard (|A∩B| / |A∪B|) was tried first and validated against
the real SDS corpus in corpus/raw/ -- it collapses to near-zero whenever one
set is much larger than the other, which real SDS documents always are (a
3-token query against a ~700-1000-unique-token document). Measured on this
project's real corpus: a genuinely correct match for the query "sodium
hydroxide corrosive" (all 3 tokens present) scored Jaccard = 0.00407, while
unrelated documents scored 0.001-0.002 -- a real signal, but on a scale no
fixed threshold can be set for without being re-tuned per corpus size, which
defeats the point of a reusable default. Step 2 instead uses the overlap
coefficient (|A∩B| / min(|A|, |B|)) -- "what fraction of the query's terms
does this candidate contain" -- which stays on a stable, corpus-size-
independent 0-1 scale. Recomputed on the same real query: the correct match
scores 1.0 (all 3 query terms present), and the closest false positives
score 0.667 (2 of 3) -- a threshold in between cleanly separates them,
something no fixed Jaccard threshold could do here.

Why hand-built and not reused from `agents/agent_a_retrieval/tfidf_ranker.py`:
    Lab 06A's deliverable is this elimination *structure* itself (which terms
    to trust, which documents survive), not a ranking score -- TF-IDF/cosine
    is Lab 05's sklearn-based deliverable and runs *after* this, only over
    whatever survives elimination. Conflating the two would demonstrate
    neither lab cleanly.

Why this exists at all, per the plan: elimination trades a little relevance
for a lot of speed. The evaluation's latency column (Layer 1) is the entire
point of this technique existing -- it is meant to be compared against
unfiltered TF-IDF ranking, not treated as a strict improvement.
"""

from __future__ import annotations

from agents.agent_a_retrieval.tfidf_ranker import RankedPassage, TfidfRanker
from indexing.inverted_index import InvertedIndex
from preprocessing.pipeline import preprocess_query


def _overlap_coefficient(query_set: set[str], doc_set: set[str]) -> float:
    """Fraction of `query_set` found in `doc_set`; 0.0 if either is empty.

    Normalises by the smaller set (the query) rather than the union, unlike
    plain Jaccard -- see the module docstring for the real-corpus
    measurements that motivated this over Jaccard for this specific step.
    """
    if not query_set or not doc_set:
        return 0.0
    return len(query_set & doc_set) / min(len(query_set), len(doc_set))


class IndexEliminator:
    """Trims a query's candidate document set before TF-IDF ranking runs.

    Example:
        >>> eliminator = IndexEliminator(inverted_index, doc_tokens)
        >>> candidates = eliminator.eliminate("store below 25 C toluene")
    """

    def __init__(
        self, inverted_index: InvertedIndex, doc_tokens: dict[str, list[str]]
    ) -> None:
        """
        Args:
            inverted_index: Built inverted index covering the same corpus.
            doc_tokens: doc_id -> that document's full preprocessed token
                list (e.g. ProcessedDocument.tokens), needed for the Jaccard
                step -- the inverted index alone only stores term frequency,
                not each document's full token set.
        """
        self._index = inverted_index
        self._doc_token_sets = {
            doc_id: set(tokens) for doc_id, tokens in doc_tokens.items()
        }

    def eliminate(
        self,
        query: str,
        top_k_terms: int = 3,
        overlap_threshold: float = 0.5,
    ) -> set[str]:
        """Return a reduced candidate set of doc_ids for `query`.

        Args:
            query: Raw query text (preprocessed internally with the same
                pipeline the corpus was indexed with -- Lab 02's invariant).
            top_k_terms: How many of the query's highest-IDF terms to use
                for candidate generation from the inverted index.
            overlap_threshold: Minimum fraction of the query's tokens that
                must be present in a candidate document's token set to
                survive the second elimination step (0.5 = at least half the
                query's distinct terms). See the module docstring for why
                this is an overlap coefficient and not plain Jaccard.

        Returns:
            Set of doc_ids that survived both elimination steps. Empty if
            the query has no terms in the index at all.
        """
        query_tokens = preprocess_query(query)
        if not query_tokens:
            return set()

        # Step 1: keep only the highest-IDF query terms -- and, critically,
        # actively exclude terms with IDF == 0 (present in *every* indexed
        # document) rather than merely capping how many terms are used.
        # Measured bug this fixes: a 3-term query where 2 of the 3 terms are
        # universal boilerplate (e.g. "flammable"/"storage", present on
        # every real SDS in this corpus) previously still selected all 3
        # under `top_k_terms=3`, and a universal term alone is enough to
        # pull every document into the candidate set -- eliminating nothing.
        distinct_terms = set(query_tokens)
        term_idfs = {
            term: self._index.inverse_document_frequency(term)
            for term in distinct_terms
        }
        max_idf = max(term_idfs.values(), default=0.0)
        if max_idf > 0:
            discriminative_terms = {t for t, idf in term_idfs.items() if idf > 0}
        else:
            # Every query term is universal (or unindexed) -- nothing to
            # discriminate on, so fall back to the full term set rather
            # than eliminating every document by definition.
            discriminative_terms = distinct_terms

        ranked_by_idf = sorted(
            discriminative_terms, key=lambda term: term_idfs[term], reverse=True
        )
        selected_terms = set(ranked_by_idf[:top_k_terms])

        candidates: set[str] = set()
        for term in selected_terms:
            candidates |= self._index.doc_ids_for_term(term)

        if not candidates:
            return set()

        # Step 2: overlap-coefficient pre-filter, using the same selected
        # term set step 1 used -- see module docstring for why overlap
        # coefficient and not plain Jaccard.
        return {
            doc_id
            for doc_id in candidates
            if _overlap_coefficient(
                selected_terms, self._doc_token_sets.get(doc_id, set())
            )
            >= overlap_threshold
        }


def rank_with_elimination(
    query: str,
    eliminator: IndexEliminator,
    passages: dict[str, str],
    top_k: int = 5,
) -> list[RankedPassage]:
    """Run the full elimination -> TF-IDF ranking pipeline for one query.

    This is the intended live-alert path: elimination trims the corpus down
    to a small candidate set first, and only that reduced set is ever fed to
    `TfidfRanker`, which is what makes elimination a genuine speed win rather
    than ranking the whole corpus and discarding results afterward.

    Args:
        query: Raw query text.
        eliminator: Built over the same corpus as `passages`.
        passages: doc_id -> raw text, the full corpus elimination selects
            from. Keys must be in the same id-space `eliminator` was built
            with (typically whole documents, since `indexing.index_builder`
            currently indexes at document granularity, not per-section) --
            a mismatch here silently eliminates everything.
        top_k: Maximum ranked results to return.

    Returns:
        RankedPassage list from `TfidfRanker.rank`, scored only over the
        surviving candidates. Empty if elimination leaves no candidates.
    """
    candidate_ids = eliminator.eliminate(query)
    if not candidate_ids:
        return []

    reduced_passages = {
        unit_id: text for unit_id, text in passages.items() if unit_id in candidate_ids
    }
    if not reduced_passages:
        return []

    return TfidfRanker(reduced_passages).rank(query, top_k=top_k)
