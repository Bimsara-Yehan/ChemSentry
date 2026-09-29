"""Rule-based chat fast path for chemical safety queries (M3, Lab 06B).

STATUS: PROTOTYPE / GATED COMPONENT
-----------------------------------
This module contains an experimental, rule-based query classifier designed to
rapidly route common physical-hazard queries before invoking heavier NLP or LLM
orchestration. It is intentionally excluded from public package exports in
`agents/agent_b_analysis/__init__.py` and disconnected from production API
routes (api/main.py) to prevent unprovenanced safety assertions from being exposed
to end users.

Safety Principle & Invariants:
------------------------------
The fast path acts solely as a structural query classifier/router. Under NO
circumstances does it generate fabricated thresholds or claim a chemical reading
is SAFE or WARNING. When a query pattern matches, it yields an UNKNOWN state
with explicit instructions directing the consumer to execute the full retrieval
and evaluation pipeline (CorpusRetriever -> DeterministicSafetyEvaluator).
"""

import re
from typing import ClassVar


class ChatFastPath:
    """Fast-path rule-based query router for chemical safety queries (Lab 06B).

    Recognises common query patterns and returns UNKNOWN with a routing hint
    instead of a fabricated threshold claim. Callers must invoke the full
    CorpusRetriever -> DeterministicSafetyEvaluator pipeline to obtain a cited
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

        Problem this solves:
            Fast-tracks identification of high-frequency physical property queries
            (e.g., flash point, flammability, storage temperature) without incurring
            LLM parsing latency.

        Why this technique:
            Compiled regex heuristics match canonical inquiry phrasing in sub-millisecond
            time while strictly adhering to safety principles by returning an UNKNOWN
            classification rather than ungrounded numerical guesses.

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
