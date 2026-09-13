"""Layer 1 (retrieval quality) evaluation harness, per ChemSentry_Final_Plan.md
Part VIII: four retrieval configurations compared on P@5, R@10, MAP, and latency.

Runs every query in evaluation/benchmarks/layer1_query_set.csv against the real
document corpus (corpus/raw/), through four cumulative configurations exactly as
the plan's own table names them:
    1. Boolean only            -- InvertedIndex.boolean_query()
    2. + TF-IDF                -- TfidfRanker ranks the whole corpus
    3. + index elimination     -- IndexEliminator trims candidates before ranking
    4. + tolerant matching     -- misspelled-category queries are corrected via
                                   the Lab 04 cascade before retrieval; every
                                   other category is unaffected (there is no
                                   typo to correct), so config 4 == config 3
                                   for exact/wildcard/phrase/proximity queries
                                   by design, not by omission.

Why this benchmark is not the placeholder-vocabulary query_set.csv used by
Layer 2 (evaluation/run_layer2_eval.py): Layer 2 tests name-resolution
accuracy against a deliberately fixed 18-chemical test fixture (see that
module's docstring) and stays valid regardless of what's in corpus/raw/.
Layer 1 tests *document* retrieval quality, which only means something
against real documents -- so it needs its own ground truth
(relevant_doc_ids), built against the real corpus in corpus/raw/ specifically.
Several of Layer 2's placeholder chemicals (toluene, ammonia, xylene, ferric
chloride, sodium chlorate) have no document in this corpus at all; reusing
those queries here would score correctly-empty results as failures.

Ground truth in layer1_query_set.csv was built by direct, independent text
search against the raw extracted document text (see that file's `notes`
column) -- not by trusting this harness's own output, the same discipline
run_layer2_eval.py's docstring describes for catching its own ground-truth
errors.

Proximity queries use "term1 /N term2" syntax (N = max word distance). None
of the four configurations here understand word position -- that's what
PositionalIndex.phrase_query()/proximity_query() are for, a fifth, separate
technique not part of the plan's four-configuration comparison table. The
proximity category exists to honestly test whether *position-blind*
bag-of-words retrieval (config 1-4, feeding in "term1 term2") over- or
under-retrieves relative to true proximity, not to exercise the positional
index itself.
"""

import csv
import time
from dataclasses import dataclass, field
from pathlib import Path

from agents.agent_a_retrieval.index_elimination import IndexEliminator
from agents.agent_a_retrieval.kgram_index import KGramIndex
from agents.agent_a_retrieval.tfidf_ranker import TfidfRanker
from agents.agent_a_retrieval.tolerant_match import resolve
from agents.agent_a_retrieval.wildcard_match import resolve_wildcard
from corpus.pdf_loader import load_all_local_pdfs
from extraction.pipeline import extract_document
from indexing.index_builder import build_all_indexes
from preprocessing.pipeline import preprocess_query

CORPUS_RAW_DIR = Path(__file__).parent.parent / "corpus" / "raw"
QUERY_SET_PATH = Path(__file__).parent / "benchmarks" / "layer1_query_set.csv"
RESULTS_PATH = Path(__file__).parent / "results" / "layer1_retrieval_quality.md"

CONFIG_NAMES = [
    "Boolean only",
    "+ TF-IDF",
    "+ index elimination",
    "+ tolerant matching",
]


@dataclass
class ConfigRun:
    retrieved: list[str]  # ordered; Boolean's "order" is arbitrary set order
    latency_ms: float


@dataclass
class QueryEvaluation:
    query_id: str
    query_text: str
    category: str
    relevant: set[str]
    runs: dict[str, ConfigRun] = field(default_factory=dict)


def _load_queries() -> list[dict[str, str]]:
    with QUERY_SET_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _relevant_set(row: dict[str, str]) -> set[str]:
    return {d.strip() for d in row["relevant_doc_ids"].split(";") if d.strip()}


def _bag_of_words_query(query_text: str, category: str) -> str:
    """Strip proximity syntax ("term1 /N term2") down to plain words for the
    position-blind configurations. Every other category is used as-is."""
    if category != "proximity":
        return query_text
    parts = query_text.split()
    return " ".join(p for p in parts if not (p.startswith("/") and p[1:].isdigit()))


class Corpus:
    """Everything the four configurations need, built once from corpus/raw/."""

    def __init__(self, raw_dir: Path) -> None:
        self.documents = [
            extract_document(raw_text, metadata)
            for raw_text, metadata in load_all_local_pdfs(raw_dir)
        ]
        self.inverted, self.positional, self.kgram = build_all_indexes(self.documents)
        self.doc_tokens = {
            doc.metadata.document_id: doc.tokens for doc in self.documents
        }
        self.passages = {
            doc.metadata.document_id: " ".join(doc.sections.values())
            for doc in self.documents
        }
        self.tfidf = TfidfRanker(self.passages)
        self.eliminator = IndexEliminator(self.inverted, self.doc_tokens)

        # Real chemical-name vocabulary, for the tolerant-matching config --
        # distinct from agents/agent_a_retrieval/vocabulary.py's fixed test
        # fixture (see that module's docstring); this is the corpus-derived
        # equivalent, same as agents/agent_a_retrieval/corpus_retrieval.py.
        self.chemical_names = sorted(
            {doc.metadata.chemical_name for doc in self.documents}
        )
        self.name_kgram_index = KGramIndex(self.chemical_names)

        self.docs_by_chemical_name: dict[str, list[str]] = {}
        for doc in self.documents:
            self.docs_by_chemical_name.setdefault(
                doc.metadata.chemical_name, []
            ).append(doc.metadata.document_id)


def _run_boolean(corpus: Corpus, query_text: str) -> ConfigRun:
    tokens = preprocess_query(query_text)
    start = time.perf_counter()
    retrieved = corpus.inverted.boolean_query(tokens, operator="AND") if tokens else []
    latency_ms = (time.perf_counter() - start) * 1000
    return ConfigRun(retrieved=retrieved, latency_ms=latency_ms)


def _run_tfidf(corpus: Corpus, query_text: str, top_k: int = 5) -> ConfigRun:
    start = time.perf_counter()
    ranked = corpus.tfidf.rank(query_text, top_k=top_k)
    latency_ms = (time.perf_counter() - start) * 1000
    return ConfigRun(retrieved=[r.unit_id for r in ranked], latency_ms=latency_ms)


def _run_elimination(corpus: Corpus, query_text: str, top_k: int = 5) -> ConfigRun:
    """Bug found while building this harness, fixed before trusting any
    latency number: this originally built a brand-new TfidfRanker (a fresh
    TfidfVectorizer fit, re-preprocessing every surviving document from
    scratch) on every single call. That timed the cost of re-vectorising a
    corpus, not the cost of elimination -- it made "+ index elimination"
    look ~500x *slower* than plain "+ TF-IDF" in the first run of this
    script, the exact opposite of what Lab 06A exists to demonstrate.
    Fixed by reusing the one TfidfRanker fit once over the whole corpus
    (`corpus.tfidf`, same object `_run_tfidf` uses) and filtering its
    ranking down to the eliminated candidates, instead of re-fitting a
    second, smaller vector space per query."""
    start = time.perf_counter()
    candidate_ids = corpus.eliminator.eliminate(query_text)
    full_ranking = corpus.tfidf.rank(query_text, top_k=len(corpus.passages))
    filtered = [r for r in full_ranking if r.unit_id in candidate_ids][:top_k]
    latency_ms = (time.perf_counter() - start) * 1000
    return ConfigRun(retrieved=[r.unit_id for r in filtered], latency_ms=latency_ms)


def _run_tolerant(
    corpus: Corpus, query_text: str, category: str, top_k: int = 5
) -> ConfigRun:
    """Config 4: entity resolution (Lab 04) runs before document retrieval,
    for the two categories that are entity-resolution problems rather than
    document-content problems -- everything else is a pass-through to
    config 3, since there's nothing for Lab 04 to resolve.

    Misspelled: resolve() corrects the chemical name, then the corrected
    name is used as a normal TF-IDF + elimination query (config 3's path).

    Wildcard: resolve_wildcard() is not a document-content ranking
    technique -- it matches *chemical names*, potentially several at once
    (e.g. "*acid" matches three different chemicals). There is no single
    "corrected query text" to rank with the way a misspelling has one, so
    the resolved names' own documents are returned directly, unranked. Bug
    found while building this harness: without this branch, "*acid" was fed
    to Boolean/TF-IDF as the literal four-character token "*acid" (the
    tokenizer doesn't strip a glued-on "*"), which cannot ever match
    anything -- config 4 scored the same 0.00 as configs 1-3, silently
    hiding that Lab 04's wildcard resolver was never actually invoked.
    """
    if category == "wildcard":
        start = time.perf_counter()
        matched_names = resolve_wildcard(query_text, corpus.chemical_names)
        retrieved: list[str] = []
        for name in matched_names:
            retrieved.extend(corpus.docs_by_chemical_name.get(name, []))
        latency_ms = (time.perf_counter() - start) * 1000
        return ConfigRun(retrieved=retrieved, latency_ms=latency_ms)

    if category != "misspelled":
        return _run_elimination(corpus, query_text, top_k=top_k)

    start = time.perf_counter()
    matches = resolve(query_text, corpus.chemical_names, corpus.name_kgram_index)
    corrected_text = matches[0].term if matches else query_text
    candidate_ids = corpus.eliminator.eliminate(corrected_text)
    full_ranking = corpus.tfidf.rank(corrected_text, top_k=len(corpus.passages))
    filtered = [r for r in full_ranking if r.unit_id in candidate_ids][:top_k]
    latency_ms = (time.perf_counter() - start) * 1000
    return ConfigRun(retrieved=[r.unit_id for r in filtered], latency_ms=latency_ms)


def run_evaluation() -> list[QueryEvaluation]:
    corpus = Corpus(CORPUS_RAW_DIR)
    evaluations = []

    for row in _load_queries():
        query_text = _bag_of_words_query(row["query_text"], row["category"])
        evaluation = QueryEvaluation(
            query_id=row["query_id"],
            query_text=row["query_text"],
            category=row["category"],
            relevant=_relevant_set(row),
        )
        evaluation.runs["Boolean only"] = _run_boolean(corpus, query_text)
        evaluation.runs["+ TF-IDF"] = _run_tfidf(corpus, query_text)
        evaluation.runs["+ index elimination"] = _run_elimination(corpus, query_text)
        evaluation.runs["+ tolerant matching"] = _run_tolerant(
            corpus, row["query_text"], row["category"]
        )
        evaluations.append(evaluation)

    return evaluations


def _precision_at_k(relevant: set[str], retrieved: list[str], k: int) -> float:
    if not relevant:
        return 1.0 if not retrieved else 0.0
    top_k = retrieved[:k]
    return len(set(top_k) & relevant) / k


def _recall_at_k(relevant: set[str], retrieved: list[str], k: int) -> float:
    if not relevant:
        return 1.0 if not retrieved else 0.0
    top_k = retrieved[:k]
    return len(set(top_k) & relevant) / len(relevant)


def _average_precision(relevant: set[str], retrieved: list[str]) -> float:
    if not relevant:
        return 1.0 if not retrieved else 0.0
    hits = 0
    precisions = []
    for i, doc_id in enumerate(retrieved, start=1):
        if doc_id in relevant:
            hits += 1
            precisions.append(hits / i)
    return sum(precisions) / len(relevant) if precisions else 0.0


@dataclass
class ConfigMetrics:
    config_name: str
    p_at_5: float
    r_at_10: float
    map_score: float
    avg_latency_ms: float


def score(evaluations: list[QueryEvaluation]) -> list[ConfigMetrics]:
    metrics = []
    for config_name in CONFIG_NAMES:
        p5s, r10s, aps, latencies = [], [], [], []
        for evaluation in evaluations:
            run = evaluation.runs[config_name]
            p5s.append(_precision_at_k(evaluation.relevant, run.retrieved, 5))
            r10s.append(_recall_at_k(evaluation.relevant, run.retrieved, 10))
            aps.append(_average_precision(evaluation.relevant, run.retrieved))
            latencies.append(run.latency_ms)
        metrics.append(
            ConfigMetrics(
                config_name=config_name,
                p_at_5=sum(p5s) / len(p5s),
                r_at_10=sum(r10s) / len(r10s),
                map_score=sum(aps) / len(aps),
                avg_latency_ms=sum(latencies) / len(latencies),
            )
        )
    return metrics


def render_report(
    evaluations: list[QueryEvaluation], metrics: list[ConfigMetrics]
) -> str:
    lines = [
        "# Layer 1 Evaluation -- Retrieval Quality",
        "",
        "Generated by `evaluation/run_layer1_eval.py` against "
        "`evaluation/benchmarks/layer1_query_set.csv`, run over the real "
        "document corpus in `corpus/raw/` (gitignored -- re-running this "
        "script requires the same PDFs, or produces different documents "
        "entirely if the corpus has changed).",
        "",
        "## Summary by configuration",
        "",
        "The latency column is the point of index elimination existing at "
        "all -- it should trade a little relevance for a lot of speed "
        "relative to `+ TF-IDF` (Lab 06A). Boolean-only's P@5/R@10 numbers "
        "are computed over an *unordered* set (Boolean retrieval has no "
        "ranking) -- treat them as a baseline for what ranking (TF-IDF) "
        "fixes, not a fully comparable ranked score.",
        "",
        "| Configuration | P@5 | R@10 | MAP | Avg latency (ms) |",
        "|---|---|---|---|---|",
    ]
    for m in metrics:
        lines.append(
            f"| {m.config_name} | {m.p_at_5:.2f} | {m.r_at_10:.2f} | "
            f"{m.map_score:.2f} | {m.avg_latency_ms:.2f} |"
        )

    lines += [
        "",
        "## Summary by category (using the `+ tolerant matching` configuration)",
        "",
        "| Category | Queries | Avg P@5 | Avg R@10 | Avg MAP |",
        "|---|---|---|---|---|",
    ]
    for category in sorted({e.category for e in evaluations}):
        cat_evals = [e for e in evaluations if e.category == category]
        p5s = [
            _precision_at_k(e.relevant, e.runs["+ tolerant matching"].retrieved, 5)
            for e in cat_evals
        ]
        r10s = [
            _recall_at_k(e.relevant, e.runs["+ tolerant matching"].retrieved, 10)
            for e in cat_evals
        ]
        aps = [
            _average_precision(e.relevant, e.runs["+ tolerant matching"].retrieved)
            for e in cat_evals
        ]
        lines.append(
            f"| {category} | {len(cat_evals)} | {sum(p5s)/len(p5s):.2f} | "
            f"{sum(r10s)/len(r10s):.2f} | {sum(aps)/len(aps):.2f} |"
        )

    lines += [
        "",
        "## Per-query detail (`+ tolerant matching` configuration)",
        "",
        "| Query | Text | Category | Relevant | Retrieved | AP |",
        "|---|---|---|---|---|---|",
    ]
    for e in evaluations:
        run = e.runs["+ tolerant matching"]
        relevant_str = "; ".join(sorted(e.relevant)) or "(none)"
        retrieved_str = "; ".join(run.retrieved) or "(none)"
        ap = _average_precision(e.relevant, run.retrieved)
        lines.append(
            f"| {e.query_id} | `{e.query_text}` | {e.category} | {relevant_str} | "
            f"{retrieved_str} | {ap:.2f} |"
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

    evaluations = run_evaluation()
    metrics = score(evaluations)
    report = render_report(evaluations, metrics)
    RESULTS_PATH.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
