"""Unit tests for agents/agent_a_retrieval/corpus_retrieval.py (M2).

Uses small synthetic SDS text through the real extraction pipeline rather
than real PDF files (corpus/raw/ is gitignored and shouldn't be a CI
dependency) -- but the text goes through the same extraction/provenance-
bridge code path real PDFs do, so this exercises the real integration, not
a mock of it.
"""

from datetime import date

from agents.agent_a_retrieval.corpus_retrieval import CorpusRetriever
from extraction.models import SDSMetadata
from extraction.pipeline import extract_document


def _document(chemical_name: str, supplier: str, document_id: str, storage_line: str):
    metadata = SDSMetadata(
        document_id=document_id,
        chemical_name=chemical_name,
        supplier=supplier,
        retrieval_date=date.today(),
    )
    raw_text = f"SECTION 7: Handling and storage\n{storage_line}\n"
    return extract_document(raw_text, metadata)


def _sample_corpus() -> list:
    return [
        _document(
            "Toluene",
            "Supplier A",
            "doc_toluene",
            "Recommended storage temperature : 10 - 25 \xb0C",
        ),
        _document(
            "Acetone",
            "Supplier A",
            "doc_acetone",
            "Recommended storage temperature : 5 - 20 \xb0C",
        ),
        # Two suppliers' SDS for the same chemical -- a real conflict case.
        _document(
            "Sulfuric acid",
            "Supplier A",
            "doc_sulfuric_a",
            "Recommended storage temperature : 5 - 25 \xb0C",
        ),
        _document(
            "Sulfuric acid",
            "Supplier B",
            "doc_sulfuric_b",
            "Recommended storage temperature : 10 - 30 \xb0C",
        ),
    ]


def test_get_thresholds_resolves_exact_chemical_name() -> None:
    retriever = CorpusRetriever(_sample_corpus())
    thresholds = retriever.get_thresholds("Toluene")

    metrics = {t.metric_name: t.value for t in thresholds}
    assert metrics["max_storage_temperature"] == 25.0
    assert metrics["min_storage_temperature"] == 10.0


def test_get_thresholds_resolves_a_misspelled_chemical_name() -> None:
    """Proves the Lab 04 tolerant-matching cascade is actually wired in here,
    not just an exact-match lookup."""
    retriever = CorpusRetriever(_sample_corpus())
    thresholds = retriever.get_thresholds("Tolune")

    assert thresholds != []
    assert any(t.value == 25.0 for t in thresholds)


def test_get_thresholds_returns_empty_for_unknown_chemical() -> None:
    retriever = CorpusRetriever(_sample_corpus())
    assert retriever.get_thresholds("xyzzy nonexistent compound") == []


def test_get_thresholds_returns_evidence_from_every_matching_supplier() -> None:
    """Two suppliers' SDS for the same chemical is a real conflict for the
    reconciler to resolve -- this layer must surface both, not silently pick
    one (or worse, average/collapse them)."""
    retriever = CorpusRetriever(_sample_corpus())
    thresholds = retriever.get_thresholds("Sulfuric acid")

    max_temp_values = {
        t.value for t in thresholds if t.metric_name == "max_storage_temperature"
    }
    assert max_temp_values == {25.0, 30.0}
    suppliers = {t.supplier_name for t in thresholds}
    assert suppliers == {"Supplier A", "Supplier B"}


def test_vocabulary_reflects_real_corpus_chemical_names() -> None:
    retriever = CorpusRetriever(_sample_corpus())

    assert set(retriever.vocabulary) == {"toluene", "acetone", "sulfuric acid"}
