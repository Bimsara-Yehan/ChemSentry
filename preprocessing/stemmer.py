"""Selective stemmer for SDS documents (M1, Lab 02).

DELIBERATE DIVERGENCE FROM LAB 02 (plan §27):
    Lab 02 stems every token with PorterStemmer.  In chemistry text, that
    collapses 'chlorate' and 'chloride' into the same stem — two substances
    with very different hazards.

    This module stems general English words (improving recall for queries
    like 'stored' → 'store') but PROTECTS chemical terms whose suffixes
    carry identity, not grammar.

Protected suffixes and why:
    -ate   chlorate ≠ chloride (different oxidation states, different hazards)
    -ide   sulfide ≠ sulfate
    -ite   sulfite ≠ sulfate
    -ol    methanol, ethanol (specific chemicals, not inflections)
    -one   acetone, cyclohexanone
    -ene   toluene, benzene, styrene
    -ane   methane, propane, butane
    -ine   chlorine, bromine, amine
    -yl    methyl, ethyl, vinyl (functional groups)
    -oxy   methoxy, ethoxy

Also protected: any token matching a CAS number pattern, and any token
containing digits (chemical identifiers like '2-butanone' or 'h301').
"""

from __future__ import annotations

import re

import nltk

# Ensure punkt tokenizer data is available.
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt", quiet=True)

try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    nltk.download("punkt_tab", quiet=True)

from nltk.stem import PorterStemmer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_stemmer = PorterStemmer()

# Chemical suffixes that must NOT be stemmed — these distinguish substances.
_CHEMICAL_SUFFIXES: tuple[str, ...] = (
    "ate",
    "ide",
    "ite",
    "ol",
    "one",
    "ene",
    "ane",
    "ine",
    "yl",
    "oxy",
    "ase",
    "ose",
)

# Regex for tokens containing digits — likely chemical identifiers, not English.
_HAS_DIGIT = re.compile(r"\d")

# CAS number pattern (already lowercased by the tokenizer).
_CAS_PATTERN = re.compile(r"^\d{2,7}-\d{2}-\d$")

# Minimum length for a token to be worth stemming — very short tokens
# are either abbreviations or chemical symbols and should be left alone.
_MIN_STEM_LENGTH = 4


def _should_protect(token: str) -> bool:
    """Return True if this token should NOT be stemmed.

    A token is protected if:
        - It contains digits (likely a chemical ID, code, or value).
        - It matches a CAS number pattern.
        - It ends with a known chemical suffix AND is long enough to be
          a plausible chemical name (not 'late', 'side', 'done').
    """
    # Tokens with digits are never English grammar.
    if _HAS_DIGIT.search(token):
        return True

    # CAS numbers (redundant with digit check, but explicit is good).
    if _CAS_PATTERN.match(token):
        return True

    # Chemical suffix protection — only for tokens long enough to be
    # chemical names.  'ate' alone (3 chars) is not a chemical; 'chlorate'
    # (8 chars) is.  Threshold: suffix_length + 3 (arbitrary but safe).
    for suffix in _CHEMICAL_SUFFIXES:
        if token.endswith(suffix) and len(token) >= len(suffix) + 3:
            return True

    return False


def selective_stem(tokens: list[str]) -> list[str]:
    """Stem tokens selectively, protecting chemical identifiers.

    General English words are stemmed with PorterStemmer to improve recall
    (e.g. 'stored' → 'store', 'handling' → 'handl').  Chemical terms whose
    suffixes carry chemical identity are left unchanged.

    Args:
        tokens: List of lowercase tokens (output of stopword removal).

    Returns:
        List of tokens, with non-chemical words stemmed.

    Example:
        >>> selective_stem(['stored', 'chlorate', 'handling', 'toluene'])
        ['store', 'chlorate', 'handl', 'toluene']
    """
    result: list[str] = []
    for token in tokens:
        if len(token) < _MIN_STEM_LENGTH or _should_protect(token):
            result.append(token)
        else:
            result.append(_stemmer.stem(token))
    return result
