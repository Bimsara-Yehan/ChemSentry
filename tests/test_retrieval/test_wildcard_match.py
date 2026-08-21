"""Tests for prefix/suffix wildcard resolution (Lab 04 / L3).

Cases mirror evaluation/benchmarks/query_set.csv's wildcard rows (Q021-Q030), plus
the token-internal case that motivated the direct-scan design over reusing the
whole-string-anchored k-gram index -- see wildcard_match.py's module docstring.
"""

from agents.agent_a_retrieval.vocabulary import VOCABULARY
from agents.agent_a_retrieval.wildcard_match import resolve_wildcard


def test_suffix_wildcard_matches_single_term():
    assert resolve_wildcard("*chlorate", VOCABULARY) == ["sodium chlorate"]


def test_prefix_wildcard_matches_first_token():
    results = resolve_wildcard("hydro*", VOCABULARY)
    assert set(results) == {
        "hydrochloric acid",
        "sodium hydroxide",
        "hydrogen peroxide",
    }


def test_prefix_wildcard_matches_multi_word_prefix_with_trailing_space():
    # "sodium *" -- the space before '*' still means "first token is sodium",
    # not "literally starts with 'sodium '".
    results = resolve_wildcard("sodium *", VOCABULARY)
    assert set(results) == {
        "sodium hydroxide",
        "sodium chlorate",
        "sodium hypochlorite",
    }


def test_prefix_wildcard_matches_a_non_first_token():
    # "per*" only matches "hydrogen peroxide" via its *second* token -- the case a
    # whole-string-anchored k-gram index can't handle without per-token indexing.
    results = resolve_wildcard("per*", VOCABULARY)
    assert set(results) == {"hydrogen peroxide", "potassium permanganate"}


def test_wildcard_with_no_match_returns_empty_list():
    assert resolve_wildcard("*ane", VOCABULARY) == []


def test_malformed_pattern_with_no_wildcard_returns_empty_list():
    assert resolve_wildcard("toluene", VOCABULARY) == []


def test_malformed_pattern_with_two_wildcards_returns_empty_list():
    assert resolve_wildcard("*chlor*ate", VOCABULARY) == []


def test_mid_term_wildcard_is_not_supported():
    # A wildcard that's neither the first nor the last character isn't a
    # supported prefix/suffix pattern -- see module docstring.
    assert resolve_wildcard("hy*ide", VOCABULARY) == []


def test_bare_wildcard_returns_empty_list():
    assert resolve_wildcard("*", VOCABULARY) == []
