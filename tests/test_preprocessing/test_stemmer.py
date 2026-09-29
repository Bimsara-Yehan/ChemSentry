"""Unit tests for the selective chemistry stemmer (M1, Lab 02 divergence).

Problem this solves:
Lab 02 stems every token with PorterStemmer, which collapses distinct chemical substances
with different hazard profiles (e.g., 'chlorate' and 'chloride' collapsed or mangled).

Why this technique:
The selective stemmer stems general English words (e.g., 'storing' -> 'store') to boost
recall, while explicitly protecting chemical suffixes (-ate, -ide, -ol, -ene, etc.) and
identifiers with digits (CAS numbers, H-codes) whose suffixes denote chemical identity.
"""

from nltk.stem import PorterStemmer

from preprocessing.stemmer import _should_protect, selective_stem


def test_selective_stemming_vs_porter_on_chemical_suffixes():
    """Verify that chemical identity suffixes survive stemming intact.

    Problem this solves: Demonstrates divergence from Lab 02 reference stemmer.
    Why this technique: Contrasts standard PorterStemmer vs selective_stem() across chemical suffixes.
    """
    chemical_terms = [
        "chlorate",  # -ate
        "chloride",  # -ide
        "sulfite",  # -ite
        "methanol",  # -ol
        "ethanol",  # -ol
        "acetone",  # -one
        "toluene",  # -ene
        "benzene",  # -ene
        "methane",  # -ane
        "chlorine",  # -ine
        "methyl",  # -yl
    ]

    stemmed = selective_stem(chemical_terms)
    for term, stemmed_term in zip(chemical_terms, stemmed):
        assert _should_protect(term) is True, f"'{term}' should be flagged as chemical"
        assert (
            stemmed_term == term
        ), f"Chemical term '{term}' was altered to '{stemmed_term}'"


def test_english_words_stemmed_normally():
    """Verify that general English words are stemmed according to standard Porter rules.

    Problem this solves: Preserves recall improvements for common morphological variants.
    Why this technique: Checks standard inflectional stems (e.g. 'storing' -> 'store').
    """
    english_words = ["storing", "operating", "containers", "protective"]
    stemmed = selective_stem(english_words)
    porter = PorterStemmer()
    expected = [porter.stem(w) for w in english_words]
    assert stemmed == expected
    assert "store" in stemmed[0]


def test_tokens_with_digits_are_protected_from_stemming():
    """Verify that identifiers containing digits (CAS numbers, H-codes, isomer names) are not stemmed.

    Problem this solves: Prevents corrupting alphanumeric chemical codes.
    Why this technique: Validates digit protection heuristic.
    """
    coded_terms = ["78-93-3", "h301", "2-butanone", "p280"]
    stemmed = selective_stem(coded_terms)
    assert stemmed == coded_terms
