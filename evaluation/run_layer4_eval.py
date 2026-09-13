"""Layer 4 (conflict detection) evaluation harness, per
ChemSentry_Final_Plan.md Part VIII: true conflicts detected vs. false
conflicts vs. missed conflicts.

Exercises agents/agent_b_analysis/reconciler.py's two conflict-detection
mechanisms directly:
    - `select_authoritative_threshold()` -- numeric variance across
      equal-authority sources, tolerance-gated (DEFAULT_CONFLICT_TOLERANCE_PCT).
    - `detect_hazard_conflicts()` -- Jaccard similarity across hazard
      statement sets, threshold-gated (default 0.6).

Ground truth in evaluation/benchmarks/layer4_conflict_scenarios.csv mixes
real and synthetic inputs, labelled per row:
    - The one real multi-supplier case in this corpus (sulfuric acid, two
      documents) is used as a genuine non-conflict (both agree exactly).
    - The hazard-conflict scenarios use REAL H-codes extracted this session
      from five real chemicals (acetone, 2-propanol, sodium hydroxide,
      sulfuric acid, hydrochloric acid, sodium bicarbonate, urea) -- these
      are real hazard profiles being compared, not invented codes, even
      though the *pairing* (asking "does the reconciler agree these two
      chemicals' hazard sets align") is constructed for this evaluation
      rather than something the corpus itself poses as a question.
    - The numeric-conflict boundary scenarios (N002-N005) are synthetic:
      this corpus has no second real multi-supplier case with genuinely
      disagreeing values, so the tolerance boundary itself (exactly 5% vs
      just over) is tested with constructed values -- the same honest gap
      Layer 5's docstring notes for its one synthetic scenario.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from agents.agent_b_analysis.reconciler import EvidenceReconciler
from agents.protocols.schemas import ProvenancedThreshold, ThresholdDirection

SCENARIOS_PATH = Path(__file__).parent / "benchmarks" / "layer4_conflict_scenarios.csv"
RESULTS_PATH = Path(__file__).parent / "results" / "layer4_conflict_detection.md"


@dataclass
class ConflictCheck:
    scenario_id: str
    mechanism: str
    description: str
    expected_conflict: bool
    actual_conflict: bool
    detail: str
    category: str  # "true_conflict_detected" | "false_conflict_avoided" | "missed_conflict" | "false_positive"


def _load_scenarios() -> list[dict[str, str]]:
    with SCENARIOS_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _run_numeric_scenario(
    row: dict[str, str], reconciler: EvidenceReconciler
) -> ConflictCheck:
    thresholds = [
        ProvenancedThreshold(
            metric_name="max_storage_temperature",
            value=float(row["input_a"]),
            unit="C",
            direction=ThresholdDirection.MAX,
            sds_id=f"{row['scenario_id']}-A",
            supplier_name="Source A",
            authority_score=1.0,
            citation=f"[{row['scenario_id']}-A] Source A",
        ),
        ProvenancedThreshold(
            metric_name="max_storage_temperature",
            value=float(row["input_b"]),
            unit="C",
            direction=ThresholdDirection.MAX,
            sds_id=f"{row['scenario_id']}-B",
            supplier_name="Source B",
            authority_score=1.0,
            citation=f"[{row['scenario_id']}-B] Source B",
        ),
    ]
    primary, notes = reconciler.select_authoritative_threshold(thresholds)
    actual_conflict = primary is None
    return ConflictCheck(
        scenario_id=row["scenario_id"],
        mechanism="numeric",
        description=f"{row['input_a']} vs {row['input_b']} (max_storage_temperature)",
        expected_conflict=row["expected_conflict"] == "True",
        actual_conflict=actual_conflict,
        detail=notes[-1],
        category="",
    )


def _parse_hazard_set(raw: str) -> set[str]:
    return {code.strip() for code in raw.split(";") if code.strip()}


def _run_hazard_scenario(
    row: dict[str, str], reconciler: EvidenceReconciler
) -> ConflictCheck:
    set_a = _parse_hazard_set(row["input_a"])
    set_b = _parse_hazard_set(row["input_b"])
    has_conflict, sim_score, explanation = reconciler.detect_hazard_conflicts(
        set_a, set_b
    )
    return ConflictCheck(
        scenario_id=row["scenario_id"],
        mechanism="hazard",
        description=f"{{{row['input_a']}}} vs {{{row['input_b']}}}",
        expected_conflict=row["expected_conflict"] == "True",
        actual_conflict=has_conflict,
        detail=f"{explanation} (Jaccard={sim_score:.2f})",
        category="",
    )


def run_evaluation() -> list[ConflictCheck]:
    reconciler = EvidenceReconciler()
    checks = []
    for row in _load_scenarios():
        if row["mechanism"] == "numeric":
            check = _run_numeric_scenario(row, reconciler)
        else:
            check = _run_hazard_scenario(row, reconciler)

        if check.expected_conflict and check.actual_conflict:
            check.category = "true_conflict_detected"
        elif not check.expected_conflict and not check.actual_conflict:
            check.category = "false_conflict_avoided"
        elif check.expected_conflict and not check.actual_conflict:
            check.category = "missed_conflict"
        else:
            check.category = "false_positive"

        checks.append(check)
    return checks


def render_report(checks: list[ConflictCheck]) -> str:
    true_detected = [c for c in checks if c.category == "true_conflict_detected"]
    false_avoided = [c for c in checks if c.category == "false_conflict_avoided"]
    missed = [c for c in checks if c.category == "missed_conflict"]
    false_positive = [c for c in checks if c.category == "false_positive"]

    total_real_conflicts = len(true_detected) + len(missed)
    total_real_non_conflicts = len(false_avoided) + len(false_positive)
    conflict_recall = (
        len(true_detected) / total_real_conflicts if total_real_conflicts else 1.0
    )
    non_conflict_specificity = (
        len(false_avoided) / total_real_non_conflicts
        if total_real_non_conflicts
        else 1.0
    )

    lines = [
        "# Layer 4 Evaluation -- Conflict Detection",
        "",
        "Generated by `evaluation/run_layer4_eval.py` against "
        "`evaluation/benchmarks/layer4_conflict_scenarios.csv`, exercising "
        "`agents/agent_b_analysis/reconciler.py`'s two conflict-detection "
        "mechanisms directly (numeric variance and hazard-statement "
        "Jaccard). See the module docstring for exactly which scenarios are "
        "real corpus data vs. synthetic, and why.",
        "",
        f"- **True conflicts detected: {len(true_detected)}/{total_real_conflicts}** "
        f"(recall on real conflicts: {conflict_recall:.0%})",
        f"- **False conflicts correctly avoided: {len(false_avoided)}/{total_real_non_conflicts}** "
        f"(specificity: {non_conflict_specificity:.0%})",
        f"- **Missed conflicts: {len(missed)}**",
        f"- **False positives (flagged a non-conflict): {len(false_positive)}**",
        "",
        "## Per-scenario detail",
        "",
        "| Scenario | Mechanism | Inputs | Expected | Actual | Category | Detail |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in checks:
        lines.append(
            f"| {c.scenario_id} | {c.mechanism} | {c.description} | "
            f"{'conflict' if c.expected_conflict else 'agree'} | "
            f"{'conflict' if c.actual_conflict else 'agree'} | {c.category} | {c.detail} |"
        )

    if missed or false_positive:
        lines += ["", "## Failures", ""]
        for c in missed + false_positive:
            lines.append(f"- **{c.scenario_id}** ({c.category}): {c.detail}")

    return "\n".join(lines) + "\n"


def main() -> None:
    checks = run_evaluation()
    report = render_report(checks)
    RESULTS_PATH.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
