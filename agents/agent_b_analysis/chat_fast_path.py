"""Rule-based chat fast path for chemical safety queries (M3, Lab 06B).

High-speed keyword and regex pattern matching to identify standard query
patterns before they reach the LLM.  When a pattern is recognised the
fast path does NOT fabricate a threshold value -- it explicitly returns
UNKNOWN with an explanation directing the caller to perform proper corpus
retrieval via CorpusRetriever.

Safety principle: the fast path is only a router.  It MUST NOT claim a
threshold is "safe" or "unsafe" without a ProvenancedThreshold from a
versioned SDS document.  Returning UNKNOWN here is correct: the caller
can follow up with CorpusRetriever.get_thresholds() → DeterministicSafetyEvaluator
to get an evidence-based SAFE or WARNING result.
"""

import re
from typing import ClassVar


class ChatFastPath:
    """Fast-path rule-based query router for chemical safety queries (Lab 06B).

    Recognises common query patterns and returns UNKNOWN with a routing hint
    instead of a fabricated threshold claim.  Callers must invoke the full
    CorpusRetriever → DeterministicSafetyEvaluator pipeline to obtain a cited
    SAFE or WARNING result.
    """

    #: Patterns: (compiled_regex, metric_key, human-readable metric description)
    PATTERNS: ClassVar[list[tuple[str, str, str]]] = [
        (
            r"flash\s*point\s+of\s+([a-zA-Z0-9\s\-,]+)",
            "flash_point",
            "flash point (Section 9, Physical Properties)",
        ),
        (
            r"is\s+([a-zA-Z0-9\s\-,]+)\s+flammable",
            "flammability",
            "flammability classification (Section 2, GHS Hazards)",
        ),
        (
            r"max\s+storage\s+temp(?:erature)?\s+for\s+([a-zA-Z0-9\s\-,]+)",
            "max_storage_temperature",
            "maximum storage temperature (Section 7, Handling and Storage)",
        ),
    ]

    def match_fast_path(self, query_text: str) -> tuple[bool, str | None]:
        """Attempt fast-path pattern matching for a user safety query.

        When a known pattern is detected, returns UNKNOWN with a routing
        message.  The caller is expected to hand off to CorpusRetriever
        for evidence-based evaluation.  If no pattern matches, returns
        (False, None) so the caller can fall through to the LLM or return
        its own UNKNOWN response.

        Args:
            query_text: Raw user query text.

        Returns:
            Tuple of (is_matched: bool, response_text: str | None).
            response_text is always an UNKNOWN-class explanation when
            is_matched is True; it is None when is_matched is False.
        """
        clean_query = query_text.strip()
        for pattern, metric_key, metric_desc in self.PATTERNS:
            match = re.search(pattern, clean_query, re.IGNORECASE)
            if match:
                chemical_name = match.group(1).strip()
                response = (
                    f"UNKNOWN: Query recognised as a '{metric_desc}' request for "
                    f"'{chemical_name}'. No threshold has been retrieved yet — a "
                    f"versioned SDS document must be consulted before a SAFE or WARNING "
                    f"determination can be made. Please use the full evaluation pipeline "
                    f"(CorpusRetriever.get_thresholds('{chemical_name}') → "
                    f"DeterministicSafetyEvaluator.evaluate()) to obtain a cited result. "
                    f"[metric_key={metric_key}]"
                )
                return True, response

        return False, None
