"""Unit tests for extraction/value_extractor.py (M1, Lab 07).

Fixtures below are literal text snippets copied from real supplier SDS PDFs
(Sigma-Aldrich/GHS-EU format) processed during development -- not invented
examples. The PDFs themselves live in corpus/raw/, which is gitignored, so
these snippets are inlined here to keep the tests runnable in CI without the
source documents.
"""

from extraction.value_extractor import (
    _normalise_numeric_string,
    extract_boiling_point,
    extract_cas_numbers,
    extract_flash_point,
    extract_incompatibilities,
    extract_ppe,
    extract_storage_temp,
)

# ---------------------------------------------------------------------------
# CAS number extraction -- false positive from EU Index-No.
# ---------------------------------------------------------------------------


def test_cas_number_excludes_eu_index_number_tail() -> None:
    """Citric acid's real SDS Section 1 text: the CAS regex, before the fix,
    also matched "750-00-3" out of the EU Index-No. "607-750-00-3" and
    reported a second, bogus CAS number for the same document."""
    text = (
        "Index-No. : 607-750-00-3\n"
        "REACH No. : 01-2119457026-42-XXXX\n"
        "CAS-No. : 77-92-9\n"
    )
    results = extract_cas_numbers(text, chemical="Citric acid")
    values = [r.value for r in results]

    assert values == ["77-92-9"]


def test_cas_number_still_matches_standalone_cas() -> None:
    """A genuine standalone CAS number (not embedded in a longer index
    number) must still be extracted -- guards against the false-positive fix
    over-suppressing real matches."""
    results = extract_cas_numbers("CAS-No. : 108-88-3", chemical="Toluene")
    assert [r.value for r in results] == ["108-88-3"]


# ---------------------------------------------------------------------------
# Storage temperature -- label:value format
# ---------------------------------------------------------------------------


def test_storage_temp_label_range_conventional() -> None:
    """Conventional (non-wrapped) label:value phrasing."""
    text = "Recommended storage temperature : 15 - 25 °C"
    results = extract_storage_temp(text, chemical="Citric acid")
    by_claim = {r.claim_type.value: r.value for r in results}

    assert by_claim["storage_temperature_min"] == "15"
    assert by_claim["storage_temperature_max"] == "25"


def test_storage_temp_label_wrapped_across_lines() -> None:
    """Real pdfplumber output for a two-column PDF layout: the label wraps
    so "temperature" lands on the line after the value, e.g.
    citric acid's actual extracted Section 7 text was
    "Recommended storage : 15 - 25 \\ufffdC\\ntemperature" (real, confirmed)."""
    text = "Recommended storage : 15 - 25 \xb0C\ntemperature"
    results = extract_storage_temp(text, chemical="Citric acid")
    by_claim = {r.claim_type.value: r.value for r in results}

    assert by_claim["storage_temperature_min"] == "15"
    assert by_claim["storage_temperature_max"] == "25"


def test_storage_temp_label_single_value_reads_as_max() -> None:
    """A bare labelled value with no explicit min/max wording is read as a
    ceiling -- the conventional meaning on an SDS."""
    text = "Recommended storage temperature : 8 \xb0C"
    results = extract_storage_temp(text, chemical="Hydrogen peroxide")

    assert len(results) == 1
    assert results[0].claim_type.value == "storage_temperature_max"
    assert results[0].value == "8"


def test_storage_temp_label_ignores_unrelated_storage_field() -> None:
    """Regression guard: "Storage class (TRGS 510) : 11, Combustible Solids"
    must not be mistaken for a storage temperature -- there's no
    "temperature" token directly after "storage" and no °C/°F unit."""
    text = "Storage class (TRGS 510) : 11, Combustible Solids"
    results = extract_storage_temp(text, chemical="Citric acid")

    assert results == []


# ---------------------------------------------------------------------------
# PPE -- label:value material format
# ---------------------------------------------------------------------------


def test_ppe_material_label_format() -> None:
    """Real Section 8 phrasing names the glove/eyewear material under a
    "Material :" sub-label, not as a "wear X gloves" sentence."""
    text = "Hand protection\nMaterial : Nitrile rubber\nBreak through time : 480 min\n"
    results = extract_ppe(text, chemical="Citric acid")
    values = [r.value for r in results]

    assert "nitrile rubber" in values


# ---------------------------------------------------------------------------
# Incompatibility -- real Section 10 phrasing, no "incompatible" wording
# ---------------------------------------------------------------------------


def test_incompatibility_violent_reactions_phrasing() -> None:
    """Real sodium hydroxide Section 10 text: no occurrence of the words
    "incompatible"/"incompatibility" anywhere -- the same claim is phrased
    as "Violent reactions possible with:" followed by a newline-separated
    substance list, and a second hazard sub-heading follows immediately
    after with no period or blank line in between."""
    text = (
        "Violent reactions possible with:\n"
        "Acetone\n"
        "Chlorine\n"
        "Fluorine\n"
        "can decompose violently in contact with:\n"
        "Organic Substances\n"
    )
    results = extract_incompatibilities(text, chemical="Sodium hydroxide")

    assert len(results) == 2
    assert "Acetone" in results[0].value
    assert "Chlorine" in results[0].value
    # The next trigger phrase must terminate the first list, not swallow it.
    assert "Organic Substances" not in results[0].value
    assert "Organic Substances" in results[1].value


def test_incompatibility_still_matches_sentence_style() -> None:
    """Original sentence-style phrasing must still work after broadening
    the trigger phrases for the label-style real-world cases."""
    text = "Incompatible with strong oxidizers, acids."
    results = extract_incompatibilities(text, chemical="Generic solvent")

    assert len(results) == 1
    assert "oxidizers" in results[0].value


# ---------------------------------------------------------------------------
# Locale-aware numeric parsing -- European (comma-decimal, period-thousands)
# number formats, confirmed used throughout the real corpus (every document
# is from Sigma-Aldrich Chemie GmbH). Found while building Layer 5 evaluation
# ground truth: sodium hydroxide's real boiling point ("1.390 \xb0C", meaning
# 1390) was extracted as 1.39, and acetone's real flash point
# ("-17,0 \xb0C") was extracted as 0.0 -- a wrong, falsely reassuring value
# on a safety-relevant property, silently produced.
# ---------------------------------------------------------------------------


def test_normalise_numeric_string_handles_comma_decimal() -> None:
    assert _normalise_numeric_string("-17,0") == "-17.0"
    assert _normalise_numeric_string("20,0") == "20.0"


def test_normalise_numeric_string_handles_eu_thousands_separator() -> None:
    assert _normalise_numeric_string("1.390") == "1390"


def test_normalise_numeric_string_leaves_plain_values_unchanged() -> None:
    assert _normalise_numeric_string("25") == "25"
    assert _normalise_numeric_string("25.5") == "25.5"
    assert _normalise_numeric_string("-5") == "-5"


def test_flash_point_extracts_real_negative_comma_decimal_value() -> None:
    """The exact real acetone case that was silently wrong: extracted as
    0.0 before this fix, must now be -17.0."""
    text = "Flash point : -17,0 \xb0C\nMethod: closed cup"
    results = extract_flash_point(text, chemical="Acetone")

    assert len(results) == 1
    assert results[0].value == "-17.0"
    assert float(results[0].value) == -17.0


def test_boiling_point_extracts_real_thousands_separator_value() -> None:
    """The exact real sodium hydroxide case: extracted as 1.39 before this
    fix (1000x too small), must now be 1390."""
    text = "Initial boiling point 1.390 \xb0C at 1.013 hPa\nand boiling range"
    results = extract_boiling_point(text, chemical="Sodium hydroxide")

    assert len(results) == 1
    assert results[0].value == "1390"
    assert float(results[0].value) == 1390.0


def test_boiling_point_still_extracts_plain_values_correctly() -> None:
    """Regression guard: the fix must not break the common case of a plain
    value with no locale ambiguity at all."""
    text = "Boiling point: 56 \xb0C"
    results = extract_boiling_point(text, chemical="Acetone")

    assert len(results) == 1
    assert results[0].value == "56"
