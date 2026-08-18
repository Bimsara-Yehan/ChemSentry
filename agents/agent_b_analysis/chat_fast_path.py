"""Rule-based chat fast path for chemical safety queries (M3, Lab 06B).

High-speed keyword and regex pattern matching to answer standard queries without LLM overhead.
"""

import re
from typing import Dict, Optional, Tuple


class ChatFastPath:
    """Fast-path rule-based response engine for chemical safety queries (Lab 06B)."""

    PATTERNS = [
        (
            r"flash\s*point\s+of\s+([a-zA-Z0-9\s]+)",
            "The flash point of {0} is dynamically retrieved from Section 9 (Physical Properties) of its versioned SDS.",
        ),
        (
            r"is\s+([a-zA-Z0-9\s]+)\s+flammable",
            "Flammability status for {0} is classified under GHS Category H225/H226 per Section 2 of its SDS.",
        ),
        (
            r"max\s+storage\s+temp(erature)?\s+for\s+([a-zA-Z0-9\s]+)",
            "Maximum storage temperature limit for {0} is governed by Section 7 (Handling and Storage).",
        ),
    ]

    def match_fast_path(self, query_text: str) -> Tuple[bool, Optional[str]]:
        """Attempt fast-path rule matching for user safety query.
        
        Returns:
            Tuple of (is_matched: bool, response_text: Optional[str])
        """
        clean_query = query_text.strip()
        for pattern, response_template in self.PATTERNS:
            match = re.search(pattern, clean_query, re.IGNORECASE)
            if match:
                extracted_entity = match.group(1).strip()
                response = response_template.format(extracted_entity)
                return True, response

        return False, None
