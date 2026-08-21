"""Layer 2 (entity resolution) evaluation harness for the tolerant retrieval cascade
and wildcard resolver (Lab 04 / L3), per ChemSentry_Final_Plan.md Part VIII.

Runs every exact/misspelled/wildcard query in evaluation/benchmarks/query_set.csv
(Q001-Q030) through the actual retrieval code and scores it against
`expected_chemicals` -- not against a description of what the code *should* do, so a
change to resolve() or resolve_wildcard() that breaks a case shows up here, not just
in unit tests that only exercise a handful of examples. This is also how the four
ground-truth errors in query_set.csv (Q023/Q024/Q026/Q028, corrected in the same
change as this file) were caught: by cross-checking the code's output against every
row by hand before trusting either the code or the benchmark as ground truth.

Two metrics, not one, because exact/misspelled and wildcard are different tasks:
  - exact/misspelled: resolve() ranks candidates and a caller downstream would use
    the top one, so top-1 accuracy (is the #1 candidate correct?) is what actually
    matters operationally -- a correct answer buried at rank 3 wouldn't help a real
    threshold lookup.
  - wildcard: resolve_wildcard() is a "find every match" operation with no ranking,
    so set precision/recall/F1 against the full expected set is the right metric.

Phrase and proximity rows (Q031-Q050) are excluded -- they test document-content
retrieval against real SDS text that doesn't exist yet (M1's corpus/extraction/
indexing). See evaluation/benchmarks/README.md.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from agents.agent_a_retrieval.kgram_index import KGramIndex
from agents.agent_a_retrieval.tolerant_match import resolve
from agents.agent_a_retrieval.vocabulary import VOCABULARY
from agents.agent_a_retrieval.wildcard_match import resolve_wildcard

QUERY_SET_PATH = Path(__file__).parent / "benchmarks" / "query_set.csv"
RESULTS_PATH = Path(__file__).parent / "results" / "layer2_entity_resolution.md"

WILDCARD_CATEGORY = "wildcard"
LAYER2_CATEGORIES = {"exact", "misspelled", WILDCARD_CATEGORY}


@dataclass
class QueryResult:
    query_id: str
    query_text: str
    category: str
    expected: set[str]
    returned: set[str]
    correct: bool


@dataclass
class CategoryMetrics:
    category: str
    query_count: int
    pass_rate: (
        float  # top-1 accuracy for exact/misspelled; exact-set-match for wildcard
    )
    precision: float
    recall: float
    f1: float


def _load_queries() -> list[dict[str, str]]:
    with QUERY_SET_PATH.open(newline="", encoding="utf-8") as f:
        return [
            row for row in csv.DictReader(f) if row["category"] in LAYER2_CATEGORIES
        ]


def _expected_set(row: dict[str, str]) -> set[str]:
    return {
        c.strip().lower() for c in row["expected_chemicals"].split(";") if c.strip()
    }


def _run_query(row: dict[str, str], kgram_index: KGramIndex) -> QueryResult:
    expected = _expected_set(row)

    if row["category"] == WILDCARD_CATEGORY:
        returned = {t.lower() for t in resolve_wildcard(row["query_text"], VOCABULARY)}
        correct = returned == expected
    else:
        matches = resolve(row["query_text"], VOCABULARY, kgram_index)
        top1 = {matches[0].term.lower()} if matches else set()
        returned = top1
        correct = bool(top1) and top1 <= expected

    return QueryResult(
        query_id=row["query_id"],
        query_text=row["query_text"],
        category=row["category"],
        expected=expected,
        returned=returned,
        correct=correct,
    )


def _precision_recall_f1(
    expected: set[str], returned: set[str]
) -> tuple[float, float, float]:
    if not returned and not expected:
        return 1.0, 1.0, 1.0
    intersection = len(expected & returned)
    precision = intersection / len(returned) if returned else 0.0
    recall = intersection / len(expected) if expected else 0.0
    f1 = (
        (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    )
    return precision, recall, f1


def run_evaluation() -> tuple[list[QueryResult], list[CategoryMetrics]]:
    """Run every Layer 2 benchmark query and return per-query and per-category results."""
    kgram_index = KGramIndex(VOCABULARY)
    results = [_run_query(row, kgram_index) for row in _load_queries()]

    metrics = []
    for category in sorted({r.category for r in results}):
        cat_results = [r for r in results if r.category == category]
        scored = [_precision_recall_f1(r.expected, r.returned) for r in cat_results]
        precisions, recalls, f1s = zip(*scored)
        metrics.append(
            CategoryMetrics(
                category=category,
                query_count=len(cat_results),
                pass_rate=sum(r.correct for r in cat_results) / len(cat_results),
                precision=sum(precisions) / len(precisions),
                recall=sum(recalls) / len(recalls),
                f1=sum(f1s) / len(f1s),
            )
        )
    return results, metrics


def render_report(results: list[QueryResult], metrics: list[CategoryMetrics]) -> str:
    lines = [
        "# Layer 2 Evaluation -- Entity Resolution",
        "",
        "Generated by `evaluation/run_layer2_eval.py` against "
        "`evaluation/benchmarks/query_set.csv` (Q001-Q030: exact, misspelled, wildcard).",
        "Phrase/proximity queries (Q031-Q050) are excluded -- see that directory's README.",
        "",
        "## Summary by category",
        "",
        "| Category | Queries | Pass rate | Precision | Recall | F1 |",
        "|---|---|---|---|---|---|",
    ]
    for m in metrics:
        lines.append(
            f"| {m.category} | {m.query_count} | {m.pass_rate:.0%} | "
            f"{m.precision:.2f} | {m.recall:.2f} | {m.f1:.2f} |"
        )

    lines += [
        "",
        "## Per-query results",
        "",
        "| Query | Text | Category | Expected | Returned | Result |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        expected_str = "; ".join(sorted(r.expected)) or "(none)"
        returned_str = "; ".join(sorted(r.returned)) or "(none)"
        lines.append(
            f"| {r.query_id} | `{r.query_text}` | {r.category} | {expected_str} | "
            f"{returned_str} | {'PASS' if r.correct else 'FAIL'} |"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    results, metrics = run_evaluation()
    report = render_report(results, metrics)
    RESULTS_PATH.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
