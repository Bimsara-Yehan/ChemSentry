"""GHS section splitter for Safety Data Sheets (M1, Lab 07).

A standard SDS follows the Globally Harmonised System (GHS) with 16 numbered
sections.  This module splits raw SDS text into those sections so that
downstream extraction can target the right section for each value type:
    - Section 7:  Handling and storage  → storage temperature limits
    - Section 8:  Exposure controls / PPE → PPE requirements, exposure limits
    - Section 10: Stability and reactivity → incompatibilities

Why regex and not an LLM?
    The plan (§13) mandates: "the LLM never touches the safety-decision path."
    Section identification is on the critical path to extracting safety values,
    so it must be deterministic.  A regex that fails visibly is safer than an
    LLM that fails silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# GHS section titles (standard across all compliant SDS documents)
# ---------------------------------------------------------------------------

GHS_SECTION_TITLES: dict[int, str] = {
    1: "Identification",
    2: "Hazard(s) identification",
    3: "Composition / information on ingredients",
    4: "First-aid measures",
    5: "Fire-fighting measures",
    6: "Accidental release measures",
    7: "Handling and storage",
    8: "Exposure controls / personal protection",
    9: "Physical and chemical properties",
    10: "Stability and reactivity",
    11: "Toxicological information",
    12: "Ecological information",
    13: "Disposal considerations",
    14: "Transport information",
    15: "Regulatory information",
    16: "Other information",
}


# ---------------------------------------------------------------------------
# Section-heading regex
# ---------------------------------------------------------------------------

# Matches lines like:
#   "SECTION 7: Handling and storage"
#   "Section 7 – Handling and Storage"
#   "7. Handling and storage"
#   "7  HANDLING AND STORAGE"
#
# Captures:  group(1) = section number
_SECTION_HEADING_RE = re.compile(
    r"^\s*(?:SECTION\s+)?(\d{1,2})\s*[.:–\-]\s*(.+)",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass
class SectionSplit:
    """Result of splitting an SDS into sections."""

    sections: dict[int, str]
    """section_number → section text (without the heading line itself)."""

    unmatched_header: str
    """Text before the first recognised section heading (e.g. cover page)."""

    section_count: int
    """Number of sections successfully identified."""


def split_sections(raw_text: str) -> SectionSplit:
    """Split raw SDS text into its GHS-numbered sections.

    The algorithm scans for section headings (e.g. "SECTION 7: Handling and
    storage") and assigns all text between consecutive headings to the
    earlier section number.

    Args:
        raw_text: Full text of an SDS document (from PDF extraction or HTML).

    Returns:
        SectionSplit with sections dict, any unmatched header text, and count.

    Example:
        >>> result = split_sections(
        ...     "SECTION 7: Handling and storage\\nStore below 25 C.\\n"
        ...     "SECTION 8: Exposure controls\\nWear gloves.\\n"
        ... )
        >>> result.sections[7]
        'Store below 25 C.'
        >>> result.sections[8]
        'Wear gloves.'
    """
    if not raw_text or not raw_text.strip():
        return SectionSplit(sections={}, unmatched_header="", section_count=0)

    # Find all section headings with their positions.
    headings: list[tuple[int, int, int]] = []  # (match_start, match_end, section_num)
    for match in _SECTION_HEADING_RE.finditer(raw_text):
        section_num = int(match.group(1))
        if 1 <= section_num <= 16:
            headings.append((match.start(), match.end(), section_num))

    if not headings:
        # No sections found — return entire text as unmatched.
        return SectionSplit(
            sections={}, unmatched_header=raw_text.strip(), section_count=0
        )

    # Sort by position in document (they should already be in order, but
    # some SDS documents have appendices that repeat section numbers).
    headings.sort(key=lambda h: h[0])

    # Extract text between consecutive headings.
    sections: dict[int, str] = {}
    unmatched_header = raw_text[: headings[0][0]].strip()

    for i, (_, end, sec_num) in enumerate(headings):
        if i + 1 < len(headings):
            next_start = headings[i + 1][0]
            section_text = raw_text[end:next_start].strip()
        else:
            section_text = raw_text[end:].strip()

        # If the same section appears twice (rare), concatenate.
        if sec_num in sections:
            sections[sec_num] += "\n" + section_text
        else:
            sections[sec_num] = section_text

    return SectionSplit(
        sections=sections,
        unmatched_header=unmatched_header,
        section_count=len(sections),
    )
