"""Unit tests for ChatFastPath (Lab 06B)."""

import pytest
from agents.agent_b_analysis.chat_fast_path import ChatFastPath


@pytest.fixture
def fast_path() -> ChatFastPath:
    return ChatFastPath()


def test_match_flash_point(fast_path: ChatFastPath) -> None:
    matched, resp = fast_path.match_fast_path("What is the flash point of Acetone?")
    assert matched is True
    assert resp is not None
    assert "Acetone" in resp
    assert "Section 9" in resp


def test_match_flammability(fast_path: ChatFastPath) -> None:
    matched, resp = fast_path.match_fast_path("Is Toluene flammable")
    assert matched is True
    assert resp is not None
    assert "Toluene" in resp
    assert "Section 2" in resp


def test_unmatched_complex_query(fast_path: ChatFastPath) -> None:
    matched, resp = fast_path.match_fast_path("Synthesize a 5-step emergency response plan for zone 4 spill")
    assert matched is False
    assert resp is None
