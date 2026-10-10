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


def test_get_thresholds_ignores_case_and_whitespace() -> None:
    retriever = CorpusRetriever(_sample_corpus())
    thresholds = retriever.get_thresholds("  SULFURIC   Acid ")

    assert {t.sds_id for t in thresholds} == {"doc_sulfuric_a", "doc_sulfuric_b"}


def test_get_thresholds_does_not_substitute_a_misspelled_name() -> None:
    """A typo gets a suggestion (below), never another document's limits --
    the safety paths call this with no person there to catch a wrong guess."""
    retriever = CorpusRetriever(_sample_corpus())
    assert retriever.get_thresholds("Tolune") == []


def test_resolve_name_suggests_the_intended_chemical_for_a_typo() -> None:
    """The Lab 04 cascade is still wired in, as a suggestion with its stage."""
    retriever = CorpusRetriever(_sample_corpus())
    match = retriever.resolve_name("Tolune")

    assert match is not None
    assert match.term == "Toluene"  # as the SDS spells it, not the index key
    assert match.stage == "edit_distance"


def test_resolve_name_reports_an_exact_match_as_exact() -> None:
    retriever = CorpusRetriever(_sample_corpus())
    match = retriever.resolve_name("sulfuric acid")

    assert match is not None
    assert match.term == "Sulfuric acid"
    assert match.stage == "exact"


def _lookalike_corpus() -> list:
    """Real corpus chemical names the cascade used to match unrelated queries to."""
    return [
        _document(
            "Ethanol",
            "Supplier A",
            "doc_ethanol",
            "Recommended storage temperature : 15 - 25 \xb0C",
        ),
        _document(
            "Hydrogen peroxide solution",
            "Supplier A",
            "doc_h2o2",
            "Recommended storage temperature : 2 - 8 \xb0C",
        ),
    ]


def test_get_thresholds_never_borrows_a_lookalike_chemicals_limits() -> None:
    """Regression: on the real corpus these queries came back with Ethanol's
    15-25 C or Hydrogen peroxide solution's 2-8 C storage limits."""
    retriever = CorpusRetriever(_lookalike_corpus())

    for query in ["Methanol", "Ethanolamine", "Hydroquinone", "Hydrazine"]:
        assert retriever.get_thresholds(query) == [], query


def test_get_thresholds_treats_a_partial_name_as_a_different_chemical() -> None:
    """ "Hydrogen peroxide" reached the solution's SDS via Soundex; the neat
    substance and a solution are not interchangeable."""
    retriever = CorpusRetriever(_lookalike_corpus())

    assert retriever.get_thresholds("Hydrogen peroxide") == []
    assert retriever.get_thresholds("Hydrogen peroxide solution") != []


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
