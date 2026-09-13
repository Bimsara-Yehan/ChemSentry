"""Layer 3 (information extraction) evaluation harness, per
ChemSentry_Final_Plan.md Part VIII: precision/recall/F1 and normalised-value
exact-match for regex-extracted values.

Runs the real extraction pipeline (extraction.pipeline.extract_document) on
every document in corpus/raw/ and compares its output against
evaluation/benchmarks/layer3_ground_truth.csv -- ground truth built by
direct, independent reading of the raw extracted text (see each row's
`notes` column), not by trusting this harness's own output, the same
discipline the Layer 1 and Layer 5 harnesses use.

Scope: CAS numbers, storage temperature (min/max), flash point, and boiling
point -- the claim types with clean, verifiable ground truth across every
document. Two named metrics from the plan are deliberately absent, honestly
rather than silently: humidity limits and occupational exposure limits
(TWA/STEL) have **zero real occurrences** anywhere in this 13-document
corpus (every document is a generic EU MSDS with "NO OEL DATA"), so no P/R/F1
can be computed for them without inventing data. PPE is also excluded from
the quantitative table for a different reason: confirmed real signal (glove
material, e.g. "nitrile rubber") is mixed with known generic noise
("protection", "respirator") from the sentence-style fallback pattern in
extraction/value_extractor.py's `_PPE_RE` -- scoring it here would produce a
number that looks precise but isn't, so it's reported qualitatively instead
of averaged into a false-confidence figure.

One caveat surfaced while building ground truth, not swept under the
"100%": hydrochloric acid's real Section 9 text is ">100 \xb0C - lit." (a
stated lower bound), but extraction reports a bare 100.0 -- the ">"
qualifier is silently dropped. Counted as a match here (the number itself is
right) but flagged in the report rather than presented as a clean case.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from corpus.pdf_loader import load_all_local_pdfs
from extraction.pipeline import extract_document

CORPUS_RAW_DIR = Path(__file__).parent.parent / "corpus" / "raw"
GROUND_TRUTH_PATH = Path(__file__).parent / "benchmarks" / "layer3_ground_truth.csv"
RESULTS_PATH = Path(__file__).parent / "results" / "layer3_extraction_quality.md"


@dataclass
class ClaimCheck:
    document_id: str
    chemical_name: str
    claim_type: str
    expected: str
    extracted: list[str]
    outcome: str  # "TP" | "FP" | "FN" | "TN"
    notes: str


def _load_ground_truth() -> list[dict[str, str]]:
    with GROUND_TRUTH_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _values_match(expected: str, extracted: str) -> bool:
    """Normalised-value exact-match: numeric comparison when both sides
    parse as numbers, exact string comparison otherwise (CAS numbers)."""
    try:
        return float(expected) == float(extracted)
    except ValueError:
        return expected.strip() == extracted.strip()


def _score_claim(row: dict[str, str], extracted_values: list[str]) -> ClaimCheck:
    expected = row["expected_value"].strip()

    if not expected:
        outcome = "TN" if not extracted_values else "FP"
    else:
        match_found = any(_values_match(expected, v) for v in extracted_values)
        outcome = "TP" if match_found else "FN"

    return ClaimCheck(
        document_id=row["document_id"],
        chemical_name=row["chemical_name"],
        claim_type=row["claim_type"],
        expected=expected or "(none)",
        extracted=extracted_values,
        outcome=outcome,
        notes=row["notes"],
    )


def run_evaluation() -> list[ClaimCheck]:
    documents_by_id = {}
    for raw_text, metadata in load_all_local_pdfs(CORPUS_RAW_DIR):
        doc = extract_document(raw_text, metadata)
        documents_by_id[metadata.document_id] = doc

    checks = []
    for row in _load_ground_truth():
        doc = documents_by_id[row["document_id"]]
        extracted_values = [
            e.value for e in doc.extractions if e.claim_type.value == row["claim_type"]
        ]
        checks.append(_score_claim(row, extracted_values))

        # Extra extracted values beyond the one that matched are spurious --
        # count each as its own false positive rather than letting a correct
        # match hide an additional wrong one (relevant for cas_number, which
        # could in principle return more than one hit per document).
        if checks[-1].outcome == "TP":
            matched_one = False
            for v in extracted_values:
                if not matched_one and _values_match(checks[-1].expected, v):
                    matched_one = True
                    continue
                checks.append(
                    ClaimCheck(
                        document_id=row["document_id"],
                        chemical_name=row["chemical_name"],
                        claim_type=row["claim_type"],
                        expected="(none, extra)",
                        extracted=[v],
                        outcome="FP",
                        notes="spurious extraction alongside a correct match",
                    )
                )

    return checks


def score(checks: list[ClaimCheck]) -> dict[str, dict[str, float]]:
    by_claim: dict[str, dict[str, int]] = {}
    for c in checks:
        by_claim.setdefault(c.claim_type, {"TP": 0, "FP": 0, "FN": 0, "TN": 0})
        by_claim[c.claim_type][c.outcome] += 1

    metrics = {}
    for claim_type, counts in by_claim.items():
        tp, fp, fn = counts["TP"], counts["FP"], counts["FN"]
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        f1 = (
            (2 * precision * recall / (precision + recall))
            if (precision + recall)
            else 0.0
        )
        metrics[claim_type] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            **counts,
        }
    return metrics


def render_report(
    checks: list[ClaimCheck], metrics: dict[str, dict[str, float]]
) -> str:
    lines = [
        "# Layer 3 Evaluation -- Information Extraction Quality",
        "",
        "Generated by `evaluation/run_layer3_eval.py` against "
        "`evaluation/benchmarks/layer3_ground_truth.csv`, run over the real "
        "document corpus in `corpus/raw/` (gitignored -- manual/local "
        "evaluation run, not CI-gated, same convention as Layers 1 and 5).",
        "",
        "**Scope note:** humidity limits and exposure limits (TWA/STEL) have "
        "zero real occurrences anywhere in this corpus (every document is a "
        "generic EU MSDS with no OEL data) -- omitted rather than scored "
        "with invented ground truth. PPE is omitted from this quantitative "
        "table for a different reason: real signal is mixed with known "
        "generic-word noise from a fallback sentence-style pattern; see the "
        "module docstring.",
        "",
        "## Summary by claim type",
        "",
        "| Claim type | Precision | Recall | F1 | TP | FP | FN | TN |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for claim_type, m in sorted(metrics.items()):
        lines.append(
            f"| {claim_type} | {m['precision']:.2f} | {m['recall']:.2f} | "
            f"{m['f1']:.2f} | {m['TP']} | {m['FP']} | {m['FN']} | {m['TN']} |"
        )

    overall_tp = sum(m["TP"] for m in metrics.values())
    overall_fp = sum(m["FP"] for m in metrics.values())
    overall_fn = sum(m["FN"] for m in metrics.values())
    overall_p = (
        overall_tp / (overall_tp + overall_fp) if (overall_tp + overall_fp) else 1.0
    )
    overall_r = (
        overall_tp / (overall_tp + overall_fn) if (overall_tp + overall_fn) else 1.0
    )
    overall_f1 = (
        (2 * overall_p * overall_r / (overall_p + overall_r))
        if (overall_p + overall_r)
        else 0.0
    )
    lines += [
        f"| **Overall** | **{overall_p:.2f}** | **{overall_r:.2f}** | "
        f"**{overall_f1:.2f}** | {overall_tp} | {overall_fp} | {overall_fn} | -- |",
        "",
        "## Per-claim detail",
        "",
        "| Document | Chemical | Claim | Expected | Extracted | Outcome | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in checks:
        extracted_str = "; ".join(c.extracted) or "(none)"
        lines.append(
            f"| {c.document_id} | {c.chemical_name} | {c.claim_type} | "
            f"{c.expected} | {extracted_str} | {c.outcome} | {c.notes} |"
        )

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

    checks = run_evaluation()
    metrics = score(checks)
    report = render_report(checks, metrics)
    RESULTS_PATH.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
