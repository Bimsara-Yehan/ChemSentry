"""Unit tests for CoStoragePatternMiner (Lab 09)."""

import pytest

from agents.agent_b_analysis.apriori_discovery import CoStoragePatternMiner


@pytest.fixture
def miner() -> CoStoragePatternMiner:
    return CoStoragePatternMiner(min_support=0.2, min_threshold_lift=1.0)


def test_discover_co_storage_rules(miner: CoStoragePatternMiner) -> None:
    transactions = [
        ["Nitric Acid", "Ethanol", "Acetone"],
        ["Nitric Acid", "Ethanol"],
        ["Nitric Acid", "Ethanol", "Sulfuric Acid"],
        ["Ethanol", "Acetone"],
        ["Nitric Acid", "Acetone"],
    ]
    rules = miner.discover_co_storage_rules(transactions)
    assert isinstance(rules, list)
    assert len(rules) > 0

    # Check rule keys
    rule = rules[0]
    assert "antecedents" in rule
    assert "consequents" in rule
    assert "support" in rule
    assert "lift" in rule
    assert "incompatibility_status" in rule


def test_incompatible_pair_flagging(miner: CoStoragePatternMiner) -> None:
    transactions = [
        ["Nitric Acid", "Ethanol"],
        ["Nitric Acid", "Ethanol"],
        ["Nitric Acid", "Ethanol"],
    ]
    rules = miner.discover_co_storage_rules(transactions)
    incompatible_rule = next(
        (r for r in rules if "REACTIVE" in r["incompatibility_status"]), None
    )
    assert incompatible_rule is not None
