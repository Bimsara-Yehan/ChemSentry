"""Layer 5 (end-to-end state accuracy) evaluation harness, per
ChemSentry_Final_Plan.md Part VIII: a confusion matrix over
{SAFE, WARNING, UNKNOWN} ground truth vs. what the real pipeline outputs.

Runs every scenario in evaluation/benchmarks/layer5_scenarios.csv through the
*real* end-to-end path -- CorpusRetriever.get_thresholds() (real PDFs in
corpus/raw/, real extraction, real provenance) -> DeterministicSafetyEvaluator
-- and compares the actual state against an independently-determined expected
state, built by hand from the real retrieved threshold values (see each
scenario's `notes` column and docs/ChemSentry_Final_Plan.md Part VIII item 5).

Ground truth for each scenario was derived from real threshold values
verified directly against the corpus (see the extraction bug fixed in
extraction/value_extractor.py earlier the same session -- these are the
*corrected* values, e.g. acetone's flash point is really -17.0C, not the
0.0C an earlier extraction bug produced), not by trusting this harness's own
output -- the same discipline evaluation/run_layer1_eval.py's docstring
describes.

UNKNOWN scenarios deliberately cover distinct real mechanisms, not the same
one repeated: no threshold extracted for that chemical+metric, a chemical
absent from the corpus entirely, and a unit mismatch against a real
retrieved threshold. One additional scenario -- a genuine authority-tied
numeric conflict between two equally-trusted sources -- is NOT built from
this corpus: the one real case of two supplier documents for the same
chemical (sulfuric acid) happens to agree exactly (both report 290.0C
boiling point), so it is not a natural conflict case. That path is instead
exercised with one clearly-labelled synthetic scenario, constructed directly
against agents/agent_b_analysis/reconciler.py and safety/state_machine.py
rather than through corpus lookup -- see `_synthetic_conflict_scenario()`.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from agents.agent_a_retrieval.corpus_retrieval import CorpusRetriever
from agents.protocols.schemas import (
    ProvenancedThreshold,
    SafetyEvaluationRequest,
    ThresholdDirection,
)
from safety.state_machine import DeterministicSafetyEvaluator

CORPUS_RAW_DIR = Path(__file__).parent.parent / "corpus" / "raw"
SCENARIOS_PATH = Path(__file__).parent / "benchmarks" / "layer5_scenarios.csv"
RESULTS_PATH = Path(__file__).parent / "results" / "layer5_state_accuracy.md"

STATES = ["SAFE", "WARNING", "UNKNOWN"]


@dataclass
class ScenarioResult:
    scenario_id: str
    description: str
    expected: str
    actual: str
    reasoning: str


def _load_scenarios() -> list[dict[str, str]]:
    with SCENARIOS_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _run_real_scenario(
    row: dict[str, str],
    retriever: CorpusRetriever,
    evaluator: DeterministicSafetyEvaluator,
) -> ScenarioResult:
    request = SafetyEvaluationRequest(
        chemical_name=row["chemical_name"],
        zone_id=row["zone_id"],
        metric_name=row["metric_name"],
        current_value=float(row["current_value"]),
        unit=row["unit"],
    )
    thresholds = [
        t
        for t in retriever.get_thresholds(row["chemical_name"])
        if t.metric_name == row["metric_name"]
    ]
    result = evaluator.evaluate(request, thresholds)

    description = (
        f"{row['chemical_name']} / {row['metric_name']} = "
        f"{row['current_value']}{row['unit']} -- {row['notes']}"
    )
    return ScenarioResult(
        scenario_id=row["scenario_id"],
        description=description,
        expected=row["expected_state"],
        actual=result.state.value,
        reasoning=result.reasoning,
    )


def _synthetic_conflict_scenario(
    evaluator: DeterministicSafetyEvaluator,
) -> ScenarioResult:
    """The one scenario not built from real corpus lookup -- see module
    docstring for why. Two equally-trusted sources disagreeing on the same
    metric by far more than the reconciler's tolerance is a real code path
    (agents/agent_b_analysis/reconciler.py's authority-tie handling) that
    deserves a test even though this corpus has no naturally-occurring
    example of it yet."""
    request = SafetyEvaluationRequest(
        chemical_name="Synthetic Solvent",
        zone_id="Zone_A",
        metric_name="max_storage_temperature",
        current_value=27.0,
        unit="C",
    )
    thresholds = [
        ProvenancedThreshold(
            metric_name="max_storage_temperature",
            value=25.0,
            unit="C",
            direction=ThresholdDirection.MAX,
            sds_id="SYNTHETIC-A",
            supplier_name="Synthetic Supplier A",
            authority_score=1.0,
            citation="[SYNTHETIC-A] Synthetic Supplier A: max_storage_temperature = 25.0 C",
        ),
        ProvenancedThreshold(
            metric_name="max_storage_temperature",
            value=45.0,
            unit="C",
            direction=ThresholdDirection.MAX,
            sds_id="SYNTHETIC-B",
            supplier_name="Synthetic Supplier B",
            authority_score=1.0,
            citation="[SYNTHETIC-B] Synthetic Supplier B: max_storage_temperature = 45.0 C",
        ),
    ]
    result = evaluator.evaluate(request, thresholds)

    return ScenarioResult(
        scenario_id="E016-SYNTHETIC",
        description=(
            "[SYNTHETIC, not from corpus/raw/] Two equal-authority sources "
            "disagreeing 25.0C vs 45.0C on the same metric -- exercises the "
            "reconciler's unresolvable-conflict path, which this real "
            "corpus's one multi-supplier case (sulfuric acid) doesn't "
            "exercise because both real documents happen to agree"
        ),
        expected="UNKNOWN",
        actual=result.state.value,
        reasoning=result.reasoning,
    )


def run_evaluation() -> list[ScenarioResult]:
    retriever = CorpusRetriever.from_local_pdfs(CORPUS_RAW_DIR)
    evaluator = DeterministicSafetyEvaluator()

    results = [
        _run_real_scenario(row, retriever, evaluator) for row in _load_scenarios()
    ]
    results.append(_synthetic_conflict_scenario(evaluator))
    return results


def build_confusion_matrix(results: list[ScenarioResult]) -> dict[tuple[str, str], int]:
    matrix = {(e, a): 0 for e in STATES for a in STATES}
    for r in results:
        matrix[(r.expected, r.actual)] += 1
    return matrix


def render_report(
    results: list[ScenarioResult], matrix: dict[tuple[str, str], int]
) -> str:
    total = len(results)
    correct = sum(1 for r in results if r.expected == r.actual)

    lines = [
        "# Layer 5 Evaluation -- End-to-End State Accuracy",
        "",
        "Generated by `evaluation/run_layer5_eval.py` against "
        "`evaluation/benchmarks/layer5_scenarios.csv`, run through the real "
        "`CorpusRetriever` -> `DeterministicSafetyEvaluator` path over the "
        "corpus in `corpus/raw/` (gitignored -- not present in CI; this is "
        "a manual/local evaluation run, same as Layer 1). One additional "
        "scenario (E016) is synthetic, not corpus-derived -- see its row "
        "below and the module docstring for why.",
        "",
        f"**Overall accuracy: {correct}/{total} ({correct/total:.0%})**",
        "",
        "## Confusion matrix (rows = ground truth, columns = system output)",
        "",
        "| Ground truth \\ System | SAFE | WARNING | UNKNOWN |",
        "|---|---|---|---|",
    ]
    for expected in STATES:
        row = [str(matrix[(expected, actual)]) for actual in STATES]
        lines.append(f"| **{expected}** | {' | '.join(row)} |")

    lines += [
        "",
        "The UNKNOWN row is the one to lead with: it's the direct evidence "
        "that the system declines to guess rather than manufacturing a "
        "confident verdict when evidence is missing, unresolvable, or "
        "incompatible -- not merely asserted, demonstrated against five "
        "real scenarios plus one synthetic conflict case.",
        "",
        "## Per-scenario detail",
        "",
        "| Scenario | Description | Expected | Actual | Match |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        match = "PASS" if r.expected == r.actual else "FAIL"
        lines.append(
            f"| {r.scenario_id} | {r.description} | {r.expected} | {r.actual} | {match} |"
        )

    mismatches = [r for r in results if r.expected != r.actual]
    if mismatches:
        lines += ["", "## Mismatches -- reasoning from the real evaluator", ""]
        for r in mismatches:
            lines.append(
                f"- **{r.scenario_id}**: expected {r.expected}, got {r.actual}"
            )
            lines.append(f"  - System reasoning: {r.reasoning}")

    return "\n".join(lines) + "\n"


def main() -> None:
    if not CORPUS_RAW_DIR.is_dir() or not any(CORPUS_RAW_DIR.glob("*.pdf")):
        print(
            f"No PDFs found in {CORPUS_RAW_DIR} -- nothing to evaluate. "
            "This script needs the real local corpus (gitignored, not present "
            "in a fresh clone or CI); it's a manual/local evaluation run, not "
            "a CI-gated test, for exactly that reason."
        )
        return

    results = run_evaluation()
    matrix = build_confusion_matrix(results)
    report = render_report(results, matrix)
    RESULTS_PATH.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
