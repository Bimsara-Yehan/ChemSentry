"""Tolerant retrieval cascade for chemical-name resolution (Lab 04 / L3).

Resolves a possibly-misspelled query to the closest known vocabulary term(s) in three
stages, each only running if the previous one didn't produce a match:

    1. Exact match           -- the common case, cheapest check
    2. k-gram + Levenshtein  -- narrows to plausible candidates via shared k-grams
                                 (KGramIndex), then ranks them by edit distance
    3. Soundex fallback      -- catches phonetic misspellings that k-gram overlap
                                 and edit distance both miss

Returns ranked candidates with a distance/confidence score and which stage produced
the match, so callers (and the evaluation harness) can see *why* a query resolved the
way it did -- consistent with the project's provenance-everywhere principle
(CLAUDE.md, ChemSentry_Final_Plan.md Part IV Section 9).
"""

from dataclasses import dataclass

from nltk.metrics.distance import edit_distance

from agents.agent_a_retrieval.kgram_index import KGramIndex
from agents.agent_a_retrieval.soundex import soundex


@dataclass
class MatchResult:
    term: str
    stage: str  # "exact" | "edit_distance" | "soundex"
    distance: int | None  # None for soundex-only matches -- no meaningful distance


def resolve(
    query: str,
    vocabulary: list[str],
    kgram_index: KGramIndex,
    max_edit_distance: int = 2,
    max_candidates: int = 5,
) -> list[MatchResult]:
    """Resolve `query` to ranked vocabulary term(s) via the tolerant cascade.

    `max_edit_distance` bounds how many character edits away a candidate is still
    considered plausible -- Lab 04's evaluation table (clean / 1 typo / 2 typos /
    phonetic) is what motivates the default of 2.
    """
    normalized = query.strip().lower()

    exact = [term for term in vocabulary if term.lower() == normalized]
    if exact:
        return [MatchResult(term=term, stage="exact", distance=0) for term in exact]

    candidates = kgram_index.candidates(normalized)
    scored = [(term, edit_distance(normalized, term.lower())) for term in candidates]
    within_threshold = sorted(
        (item for item in scored if item[1] <= max_edit_distance),
        key=lambda item: item[1],
    )
    if within_threshold:
        return [
            MatchResult(term=term, stage="edit_distance", distance=dist)
            for term, dist in within_threshold[:max_candidates]
        ]

    query_code = soundex(normalized)
    phonetic_matches = [term for term in vocabulary if soundex(term) == query_code]
    return [
        MatchResult(term=term, stage="soundex", distance=None)
        for term in phonetic_matches[:max_candidates]
    ]
