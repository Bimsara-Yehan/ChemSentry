# Evaluation Benchmarks

50 queries across five categories (exact, misspelled, wildcard, phrase, proximity), per
`ChemSentry_Final_Plan.md` Part VIII Layer 1. Owner: M2.

## `query_set.csv`

| Column | Meaning |
|---|---|
| `query_id` | Stable identifier (`Q001`-`Q050`), referenced by future eval scripts and relevance judgement files |
| `query_text` | The query itself. Wildcards use `*`; proximity queries use `term1 /N term2` meaning "within N words" |
| `category` | One of `exact`, `misspelled`, `wildcard`, `phrase`, `proximity` |
| `expected_chemicals` | For name-resolution categories (exact/misspelled/wildcard): the vocabulary term(s) the query should resolve to, semicolon-separated |
| `notes` | What the query is exercising and why |

## Status

The query set and category split are final. `expected_chemicals` for the
exact/misspelled/wildcard rows is filled in against the placeholder vocabulary in
`agents/agent_a_retrieval/vocabulary.py`, so those rows are usable for entity-resolution
evaluation (Layer 2) right now — see `evaluation/run_layer2_eval.py` and
`evaluation/results/layer2_entity_resolution.md` for the actual run.

Q023, Q024, Q026, and Q028's `expected_chemicals` were corrected: the original
hand-assessment missed matches where the pattern lands on a *non-first* token of a
multi-word term (e.g. `*ol` also matches "isopropyl **alcohol**", `per*` matches
"hydrogen **per**oxide" as already noted in Q029). Caught by cross-checking
`resolve_wildcard()`'s output against every row by hand before trusting either as
ground truth — see `evaluation/run_layer2_eval.py`'s module docstring.

Phrase and proximity rows test document-content retrieval, not name resolution, so their
`expected_chemicals` is intentionally blank — there's no real SDS text yet to hand-assess
relevance against.

## `layer1_query_set.csv`

M1's corpus/extraction/indexing work has now landed, so Layer 1 (retrieval quality) is
built — but as a **separate** query set from the one above, not an extra column on it.
Reason: `query_set.csv`'s `expected_chemicals` were hand-assessed against the placeholder
vocabulary in `agents/agent_a_retrieval/vocabulary.py` (18 chemicals invented for testing
before any real corpus existed). The real corpus in `corpus/raw/` only covers 12 of those
— several placeholder chemicals (toluene, ammonia, xylene, ferric chloride, sodium
chlorate) have no document at all. Reusing `query_set.csv`'s rows against real documents
would score correctly-empty results (nothing to find) as retrieval failures.

`layer1_query_set.csv` is a smaller (26-query), independently-verified benchmark against
the real 12-chemical corpus: `relevant_doc_ids` (not `expected_chemicals`) is the ground
truth column, built by direct text search against the raw extracted document text — see
each row's `notes` and `evaluation/run_layer1_eval.py`'s module docstring for the method.
Run via `python -m evaluation.run_layer1_eval`; results land in
`evaluation/results/layer1_retrieval_quality.md`. This script needs `corpus/raw/`
populated locally (gitignored, not present in CI) — it's a manual evaluation run, not a
CI-gated test, for that reason.

## `layer5_scenarios.csv`

End-to-end state-accuracy scenarios (chemical, metric, sensor reading, expected
SAFE/WARNING/UNKNOWN), run through the real `CorpusRetriever` → `DeterministicSafetyEvaluator`
path — not a mock threshold table. Expected states were derived by hand from real
threshold values verified directly against the corpus (see
`evaluation/run_layer5_eval.py`'s module docstring), the same discipline as
`layer1_query_set.csv`. One additional scenario is synthetic (a genuine authority-tied
conflict) since this corpus's one real multi-supplier case (sulfuric acid) happens to
have both suppliers agree — clearly labelled as such in the results, not presented as
corpus-derived. Run via `python -m evaluation.run_layer5_eval`; results land in
`evaluation/results/layer5_state_accuracy.md`. Same `corpus/raw/` dependency as Layer 1 —
manual/local run, not CI-gated.

## `layer3_ground_truth.csv`

Information-extraction ground truth (CAS numbers, storage temperature, flash point,
boiling point) for every document in the real corpus, built by direct, independent
reading of the raw extracted text — including the negative cases ("Not applicable",
"see product label") that should correctly yield no extraction. Humidity limits and
exposure limits are intentionally absent — zero real occurrences anywhere in this
corpus — and PPE is intentionally absent from the quantitative scoring for a different
reason (real signal mixed with known generic-word noise); both are explained in
`evaluation/run_layer3_eval.py`'s module docstring rather than silently skipped. Run via
`python -m evaluation.run_layer3_eval`; results land in
`evaluation/results/layer3_extraction_quality.md`. Same `corpus/raw/` dependency as
Layer 1 — manual/local run, not CI-gated.

## `layer4_conflict_scenarios.csv`

Conflict-detection scenarios exercising `agents/agent_b_analysis/reconciler.py`'s two
mechanisms (numeric variance, hazard-statement Jaccard) directly — no corpus/index
involved, so this one has **no** `corpus/raw/` dependency and is safe to run anywhere,
including CI, though it isn't currently wired into pytest as an assertion-gated test.
Hazard scenarios use real H-codes extracted from real chemicals this session (see the
script's module docstring for which); the numeric tolerance-boundary scenarios are
synthetic, since this corpus's one real multi-supplier pair (sulfuric acid) agrees
rather than disagrees. Run via `python -m evaluation.run_layer4_eval`; results land in
`evaluation/results/layer4_conflict_detection.md`.
