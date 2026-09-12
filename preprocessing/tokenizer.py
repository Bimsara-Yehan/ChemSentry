"""Chemistry-aware tokenizer for SDS documents (M1, Lab 02).

DELIBERATE DIVERGENCE FROM LAB 02 (plan §27):
    Lab 02 uses `content.split()` which fragments chemical names like
    '2-butanone' into ['2', 'butanone'] and destroys CAS numbers like
    '78-93-3' into ['78', '93', '3'].

    This tokenizer PROTECTS chemical identifier patterns before splitting,
    then restores them into the token stream.  The same principle as Lab 02's
    own warning that documents and queries must share a tokenizer, applied to
    a harder vocabulary.

Why not just use a regex tokenizer?
    A single regex that correctly handles ALL chemical naming conventions
    (IUPAC, trade names, CAS, formulas) is brittle and hard to maintain.
    The protect-split-restore approach is simpler to debug, extend, and
    explain in the viva.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Patterns that must survive tokenisation intact
# ---------------------------------------------------------------------------

# Order matters — more specific patterns first to avoid partial matches.
_PROTECTED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # CAS registry numbers:  78-93-3, 1333-74-0, 7732-18-5
    ("CAS", re.compile(r"\b\d{2,7}-\d{2}-\d\b")),
    # Concentration ranges:  1,2-dichloroethane, 2,4,6-trinitrotoluene
    ("CHEM_PREFIX", re.compile(r"\b\d(?:,\d+)*-[A-Za-z][A-Za-z\-]*[a-z]\b")),
    # Numeric ranges with units:  25–30 °C, 15-20 mg/m³
    ("RANGE_UNIT", re.compile(
        r"\b\d+\.?\d*\s*[–\-]\s*\d+\.?\d*\s*(?:°[CF]|ppm|mg/m[³3]|%)\b"
    )),
    # Standalone values with units:  ≤25 °C, >100 °F, 50 ppm
    ("VALUE_UNIT", re.compile(
        r"[<>≤≥]?\s*\d+\.?\d*\s*°[CF]"
    )),
    # H-codes and P-codes:  H301, H301+H311, P280+P310+P321
    ("HP_CODE", re.compile(
        r"\b[HP]\d{3}[A-Za-z]?(?:\s*\+\s*[HP]\d{3}[A-Za-z]?)*\b"
    )),
    # Chemical formulas:  H2O, NaOH, H2SO4, Ca(OH)2
    ("FORMULA", re.compile(
        r"\b[A-Z][a-z]?(?:\d+)?(?:\([A-Z][a-z]?\w*\)\d*)?(?:[A-Z][a-z]?\d*)*\b"
    )),
]

# Placeholder template — must not collide with real text.
_PLACEHOLDER_TEMPLATE = "\x00PROT_{idx}\x00"


@dataclass
class TokenizerResult:
    """Result of tokenisation, carrying both tokens and a mapping of
    any protected identifiers that were preserved."""

    tokens: list[str]
    protected_originals: dict[str, str] = field(default_factory=dict)


def _protect_patterns(text: str) -> tuple[str, dict[str, str]]:
    """Replace protected patterns with placeholders.

    Returns the modified text and a dict mapping placeholder → original.
    """
    mapping: dict[str, str] = {}
    counter = 0

    for _label, pattern in _PROTECTED_PATTERNS:
        for match in pattern.finditer(text):
            original = match.group()
            # Skip very short matches from the FORMULA pattern —
            # single uppercase letters like 'A', 'I' are not formulas.
            if _label == "FORMULA" and len(original) <= 2:
                continue
            placeholder = _PLACEHOLDER_TEMPLATE.format(idx=counter)
            text = text.replace(original, placeholder, 1)
            mapping[placeholder] = original
            counter += 1

    return text, mapping


def _restore_placeholders(tokens: list[str], mapping: dict[str, str]) -> list[str]:
    """Replace placeholders back with original text in the token list."""
    if not mapping:
        return tokens

    restored: list[str] = []
    for token in tokens:
        if token in mapping:
            restored.append(mapping[token].lower())
        else:
            # A token might contain a placeholder embedded in surrounding text
            for placeholder, original in mapping.items():
                token = token.replace(placeholder, original.lower())
            restored.append(token)
    return restored


def tokenize(text: str) -> list[str]:
    """Tokenize SDS text with chemical-identifier protection.

    Steps:
        1. Protect chemical patterns (CAS, hyphenated names, units, codes).
        2. Lowercase the remaining text (placeholders survive because they
           use null-byte delimiters that are case-invariant).
        3. Split on whitespace and common punctuation (except inside
           protected placeholders).
        4. Restore protected patterns back into the token stream.
        5. Remove empty tokens and single-character noise.

    Args:
        text: Raw SDS text (a single section or full document).

    Returns:
        List of lowercase tokens with chemical identifiers intact.

    Example:
        >>> tokenize("Store below 25 C. CAS: 78-93-3.")
        ['store', 'below', '25', 'cas', '78-93-3']
    """
    if not text or not text.strip():
        return []

    # Step 1: Protect chemical identifiers
    protected_text, mapping = _protect_patterns(text)

    # Step 2: Lowercase.
    # Placeholders use \x00 delimiters which are not affected by lower().
    # But the internal label "PROT" becomes "prot", so we must rebuild
    # the mapping with lowercased keys.
    protected_text = protected_text.lower()
    mapping = {k.lower(): v for k, v in mapping.items()}

    # Step 3: Split on whitespace and punctuation.
    # Keep hyphens inside words (they're common in chemical names) but split
    # on sentence-ending punctuation, commas, colons, semicolons, parentheses.
    tokens = re.split(r"[\s,;:!?\(\)\[\]{}\"/]+", protected_text)

    # Remove trailing periods (but not from protected placeholders)
    tokens = [t.rstrip(".") for t in tokens]

    # Step 4: Restore protected patterns
    tokens = _restore_placeholders(tokens, mapping)

    # Step 5: Remove empty tokens and single-character noise
    # Keep single chars only if they're meaningful (digits, certain letters)
    tokens = [t for t in tokens if len(t) > 1 or t.isdigit()]

    return tokens
