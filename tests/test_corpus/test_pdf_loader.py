"""Unit tests for corpus/pdf_loader.py (M1).

Only `build_metadata_from_section1` is tested directly with text fixtures --
`extract_text_from_pdf` is a thin pdfplumber wrapper and would need a real
PDF fixture to test meaningfully, which is out of scope here since real SDS
PDFs live in the gitignored corpus/raw/ and shouldn't be duplicated into the
repo just to exercise a library call.
"""

from corpus.pdf_loader import build_metadata_from_section1


def test_build_metadata_parses_real_section1_fields() -> None:
    """Real Section 1 text (citric acid, Sigma-Aldrich SDS) is field-labelled
    rather than free prose -- confirmed against the actual PDF."""
    section1_text = (
        "Product name : Citric acid\n"
        "Product Number : C0759\n"
        "Index-No. : 607-750-00-3\n"
        "CAS-No. : 77-92-9\n"
        "Company : Sigma-Aldrich Chemie GmbH\n"
    )
    metadata = build_metadata_from_section1(
        section1_text, document_id="c0759", source_path="corpus/raw/c0759.pdf"
    )

    assert metadata.chemical_name == "Citric acid"
    assert metadata.cas_number == "77-92-9"
    assert metadata.supplier == "Sigma-Aldrich Chemie GmbH"
    assert metadata.document_id == "c0759"


def test_build_metadata_falls_back_when_fields_missing() -> None:
    """A document missing expected Section 1 fields should not raise --
    ingesting the rest of the document's extractable values shouldn't be
    blocked by an unparsed product name."""
    metadata = build_metadata_from_section1(
        "Some unexpected layout with no labelled fields.",
        document_id="unknown_doc",
        source_path="corpus/raw/unknown_doc.pdf",
    )

    assert metadata.chemical_name == "unknown"
    assert metadata.cas_number is None
    assert metadata.supplier == "unknown"
