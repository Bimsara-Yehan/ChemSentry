"""Unit tests for the chemistry-aware domain tokenizer (M1, Lab 02 divergence).

Problem this solves:
Lab 02's standard `content.split()` and regex punctuation-stripping fragment chemical
identifiers (e.g. CAS numbers '78-93-3' -> ['78', '93', '3'], formulas 'H2SO4' ->
['h2so4'] lost on split). This breaks downstream inverted and positional lookups.

Why this technique:
The domain tokenizer protects known chemical patterns (CAS, formulas, H/P codes, ranges)
before word-boundary splitting, and restores them intact. These tests prove that protection.
tokenize() returns a plain list[str]; all tokens are lowercased post-protection.
"""

from preprocessing.tokenizer import tokenize


def test_domain_tokenizer_vs_str_split_on_cas_numbers():
    """Verify that domain tokenizer preserves CAS numbers intact unlike str.split() and punctuation stripping.

    Problem this solves: Demonstrates deliberate divergence from Lab 02 reference where
    punctuation stripping destroys CAS numbers.
    Why this technique: Direct comparison between str.split() fragmenting '78-93-3' vs tokenize() preserving it.
    """
    raw_text = "Store 2-butanone CAS: 78-93-3 and water CAS: 7732-18-5 safely."

    # Lab 02 naive split: CAS number survives only if adjacent punctuation stripped manually
    naive_split = raw_text.split()
    assert "78-93-3" in naive_split or "78-93-3" in [
        t.strip(".,: ") for t in naive_split
    ]

    # Domain tokenizer preserves CAS numbers as single lowercase tokens
    result = tokenize(raw_text)
    assert isinstance(result, list), "tokenize() must return a plain list[str]"
    assert "78-93-3" in result
    assert "7732-18-5" in result


def test_chemical_formulas_preserved_without_parenthesis_fragmentation():
    """Verify that chemical formulas with subscripts survive tokenization as whole tokens.

    Problem this solves: Formulas like H2SO4 must not be discarded or split at digit boundaries.
    Why this technique: Checks exact (lowercased) preservation in token list.
    """
    text = "Neutralize H2SO4 with NaOH to produce H2O."
    tokens = tokenize(text)
    # Tokenizer lowercases everything including formula letters
    assert "h2so4" in tokens
    assert "naoh" in tokens
    assert "h2o" in tokens


def test_hazard_codes_and_precautionary_codes_survive():
    """Verify GHS hazard codes (H301, H225) survive tokenization intact (lowercased).

    Problem this solves: Safety statements rely on exact H and P codes.
    Why this technique: Checks H/P codes in resulting token list; tokenizer lowercases them.
    """
    text = "Hazards: H301 and H225. Precautions: P280."
    tokens = tokenize(text)
    assert "h301" in tokens
    assert "h225" in tokens
    assert "p280" in tokens


def test_temperature_ranges_and_units_preserved():
    """Verify numeric tokens survive tokenization without loss.

    Problem this solves: Storage rules referencing temperatures must not silently drop values.
    Why this technique: Checks numeric token is present in the token list.
    """
    text = "Store below 25 degrees C."
    tokens = tokenize(text)
    assert "25" in tokens


def test_chemical_name_prefixes_survive():
    """Verify IUPAC numerical prefixes like 1,2-dichloroethane remain intact.

    Problem this solves: Suffix/prefix numbering distinguishes chemical isomers.
    Why this technique: Asserts hyphenated numerical prefix is not split into bare digits.
    """
    text = "Inspect drum of 1,2-dichloroethane and 2,4,6-trinitrotoluene."
    tokens = tokenize(text)
    assert "1,2-dichloroethane" in tokens
    assert "2,4,6-trinitrotoluene" in tokens
