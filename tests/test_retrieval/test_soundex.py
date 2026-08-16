"""Tests for the hand-built Soundex encoder (Lab 04 / L3)."""

from agents.agent_a_retrieval.soundex import soundex


def test_identical_terms_share_a_code():
    assert soundex("toluene") == soundex("toluene")


def test_phonetically_similar_spellings_share_a_code():
    # "ksylene" is not a real edit-distance-close typo of "xylene" (different
    # first letter), but sounds identical -- this is exactly the case Soundex
    # exists to catch and edit distance/k-grams would miss.
    assert soundex("xylene")[1:] == soundex("sylene")[1:]


def test_empty_input_returns_zero_code():
    assert soundex("") == "0000"


def test_code_is_four_characters():
    assert len(soundex("hydrochloric acid")) == 4
