"""Regression guard for the Layer 2 (entity resolution) evaluation harness.

Runs the same evaluation evaluation/run_layer2_eval.py produces its checked-in
results table from, and asserts it stays at the level already achieved
(evaluation/results/layer2_entity_resolution.md) -- so a change to resolve(),
resolve_wildcard(), the vocabulary, or the benchmark's ground truth that regresses
retrieval quality fails CI instead of only showing up if someone remembers to
re-run the harness by hand.
"""

from evaluation.run_layer2_eval import run_evaluation


def test_layer2_evaluation_is_fully_passing():
    results, metrics = run_evaluation()

    failures = [r for r in results if not r.correct]
    assert not failures, (
        "Layer 2 regression: "
        f"{[(r.query_id, r.query_text, sorted(r.expected), sorted(r.returned)) for r in failures]}"
    )

    for m in metrics:
        assert (
            m.pass_rate == 1.0
        ), f"{m.category} pass rate dropped to {m.pass_rate:.0%}"
        assert (
            m.precision == 1.0
        ), f"{m.category} precision dropped to {m.precision:.2f}"
        assert m.recall == 1.0, f"{m.category} recall dropped to {m.recall:.2f}"


def test_layer2_evaluation_covers_all_thirty_queries():
    results, _ = run_evaluation()
    assert len(results) == 30
    assert {r.query_id for r in results} == {f"Q{i:03d}" for i in range(1, 31)}
