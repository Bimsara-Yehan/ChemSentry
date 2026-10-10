"""Unit tests for corpus/pdf_loader.py (M1).

Only `build_metadata_from_section1` is tested directly with text fixtures --
`extract_text_from_pdf` is a thin pdfplumber wrapper and would need a real
PDF fixture to test meaningfully, which is out of scope here since real SDS
PDFs live in the gitignored corpus/raw/ and shouldn't be duplicated into the
repo just to exercise a library call.
"""

import json

from corpus.pdf_loader import (
    _apply_metadata_overrides,
    build_metadata_from_section1,
    override_path_for,
    write_metadata_overrides,
)


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


def test_build_metadata_parses_carl_roth_layout() -> None:
    """Verbatim pdfplumber Section 1 text from a real Carl Roth Ethanol SDS:
    the name has no colon label and the supplier block has no label at all.
    Previously both came back wrong -- "unknown" and "/undertaking" (the old
    supplier regex matched the heading's "company/undertaking")."""
    section1_text = (
        "company/undertaking\n"
        "Identification of the substance Ethanol\n"
        "Article number 9065\n"
        "EC number 200-578-6\n"
        "CAS number 64-17-5\n"
        "Identified uses: laboratory chemical\n"
        "Carl Roth GmbH + Co KG\n"
        "Schoemperlenstr. 3-5\n"
        "D-76185 Karlsruhe\n"
    )
    metadata = build_metadata_from_section1(
        section1_text, document_id="9065", source_path="corpus/raw/9065.pdf"
    )

    assert metadata.chemical_name == "Ethanol"
    assert metadata.cas_number == "64-17-5"
    assert metadata.supplier == "Carl Roth GmbH + Co KG"


def test_build_metadata_parses_panreac_layout() -> None:
    """Verbatim Section 1 text from a real PanReac (ITW Reagents) 2-Propanol
    SDS: "Trade name:" label, CAS on the line after its label, and phone
    number on the same line as the company name."""
    section1_text = (
        "\xb7 1.1 Product identifier\n"
        "\xb7 Trade name:2-Propanol\n"
        "\xb7 Article number:1090\n"
        "\xb7 CAS Number:\n"
        "67-63-0\n"
        "\xb7 1.3 Details of the supplier of the safety data sheet\n"
        "\xb7 Manufacturer/Supplier:\n"
        "PANREAC QUIMICA S.L.U. Tel. (+34) 937 489 400\n"
        "C/Garraf 2 Fax. (+34) 937 489 401\n"
    )
    metadata = build_metadata_from_section1(
        section1_text, document_id="1090", source_path="corpus/raw/1090.pdf"
    )

    assert metadata.chemical_name == "2-Propanol"
    assert metadata.cas_number == "67-63-0"
    assert metadata.supplier == "PANREAC QUIMICA S.L.U."


def test_section1_heading_is_not_mistaken_for_a_name_or_supplier() -> None:
    """The Section 1 heading itself contains "substance/" and "company/"."""
    metadata = build_metadata_from_section1(
        "SECTION 1: Identification of the substance/mixture and of the company/\nundertaking\n",
        document_id="x",
        source_path="corpus/raw/x.pdf",
    )

    assert metadata.chemical_name == "unknown"
    assert metadata.supplier == "unknown"


def test_metadata_overrides_round_trip(tmp_path) -> None:
    """Admin corrections are written beside the PDF and re-applied on load,
    which is what makes them survive a restart (the corpus is rebuilt from
    disk). Blank values are not written, so they can't erase a parsed name."""
    pdf_path = tmp_path / "abc123.pdf"
    write_metadata_overrides(pdf_path, {"chemical_name": " Ethanol ", "supplier": "  "})

    assert json.loads(override_path_for(pdf_path).read_text()) == {
        "chemical_name": "Ethanol"
    }

    metadata = build_metadata_from_section1(
        "", document_id="abc123", source_path=str(pdf_path)
    )
    _apply_metadata_overrides(pdf_path, metadata)
    assert metadata.chemical_name == "Ethanol"
    assert metadata.supplier == "unknown"


def test_malformed_override_file_is_ignored(tmp_path) -> None:
    """A corrupt sidecar must never stop the corpus from loading."""
    pdf_path = tmp_path / "abc123.pdf"
    override_path_for(pdf_path).write_text("{not json", encoding="utf-8")

    metadata = build_metadata_from_section1(
        "Product name : Acetone\n", document_id="abc123", source_path=str(pdf_path)
    )
    _apply_metadata_overrides(pdf_path, metadata)
    assert metadata.chemical_name == "Acetone"


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
