"""Tests for corpus/ingestion_audit.py (M1).

The PDFs are built here as minimal real PDF files so the audit runs through
the genuine pdfplumber -> loader -> extraction path, exactly as it does on
the real corpus. Section text mirrors real supplier layouts (Sigma-Aldrich
label:value form) used elsewhere in this test suite.
"""

import json
from datetime import datetime, timezone

from corpus.ingestion_audit import (
    CHANGED,
    NEW,
    REMOVED,
    UNCHANGED,
    audit_corpus,
    format_report,
)


def _pdf(lines: list[str]) -> bytes:
    """A one-page PDF whose text layer is `lines` (Helvetica, WinAnsi)."""

    def esc(t: str) -> str:
        return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    body = "BT /F1 10 Tf 40 800 Td 14 TL\n"
    body += "".join(f"({esc(line)}) Tj T*\n" for line in lines) + "ET"
    stream = body.encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


_H2O2 = [
    "SECTION 1: Identification of the substance/mixture and of the company/undertaking",
    "Product name : Hydrogen peroxide solution",
    "CAS-No. : 7722-84-1",
    "Company : Sigma-Aldrich Chemie GmbH",
    "SECTION 7: Handling and storage",
    "Recommended storage temperature : 2 - 8 \xb0C",
    "SECTION 9: Physical and chemical properties",
]

_NO_STORAGE = [
    "SECTION 1: Identification of the substance/mixture and of the company/undertaking",
    "Product name : Sodium hydroxide",
    "CAS-No. : 1310-73-2",
    "Company : Sigma-Aldrich Chemie GmbH",
    "SECTION 10: Stability and reactivity",
]

_T0 = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)


def _events(log):
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_new_documents_are_logged_with_what_extraction_found(tmp_path):
    (tmp_path / "216763.pdf").write_bytes(_pdf(_H2O2))
    (tmp_path / "221465.pdf").write_bytes(_pdf(_NO_STORAGE))

    report = audit_corpus(tmp_path, now=_T0)

    by_file = {d.file: d for d in report.documents}
    h2o2 = by_file["216763.pdf"]
    assert h2o2.status == NEW
    assert h2o2.chemical_name == "Hydrogen peroxide solution"
    assert h2o2.supplier == "Sigma-Aldrich Chemie GmbH"
    assert h2o2.cas_number == "7722-84-1"
    assert {(s["claim"], float(s["value"])) for s in h2o2.storage_limits} == {
        ("storage_temperature_min", 2.0),
        ("storage_temperature_max", 8.0),
    }
    assert all(
        "storage temperature" in s["source_text"].lower() for s in h2o2.storage_limits
    )
    assert not any("storage" in f for f in h2o2.findings)

    # The finding comes from the extraction output, explaining the UNKNOWN.
    naoh = by_file["221465.pdf"]
    assert any("no storage-temperature limit" in f for f in naoh.findings)
    assert any("Section 7" in f for f in naoh.findings)

    events = _events(tmp_path / ".ingestion_audit.jsonl")
    assert [e["event"] for e in events] == [NEW, NEW]
    assert {e["sha256"] for e in events} == {d.sha256 for d in report.documents}
    assert all(e["actor"] == "system" and e["at"] == _T0.isoformat() for e in events)


def test_rerun_on_unchanged_corpus_appends_nothing(tmp_path):
    (tmp_path / "216763.pdf").write_bytes(_pdf(_H2O2))
    audit_corpus(tmp_path)
    log = tmp_path / ".ingestion_audit.jsonl"
    before = log.read_text(encoding="utf-8")

    report = audit_corpus(tmp_path)

    assert [d.status for d in report.documents] == [UNCHANGED]
    assert report.events_written == 0
    assert log.read_text(encoding="utf-8") == before


def test_replaced_file_is_logged_as_changed_with_previous_hash(tmp_path):
    path = tmp_path / "216763.pdf"
    path.write_bytes(_pdf(_H2O2))
    first = audit_corpus(tmp_path).documents[0]

    revised = [line.replace("2 - 8", "2 - 10") for line in _H2O2]
    path.write_bytes(_pdf(revised))
    second = audit_corpus(tmp_path).documents[0]

    assert second.status == CHANGED
    assert second.previous_sha256 == first.sha256
    assert {float(s["value"]) for s in second.storage_limits} == {2.0, 10.0}
    events = _events(tmp_path / ".ingestion_audit.jsonl")
    assert [e["event"] for e in events] == [NEW, CHANGED]


def test_removed_file_is_logged_once_and_reappearance_is_new(tmp_path):
    path = tmp_path / "216763.pdf"
    path.write_bytes(_pdf(_H2O2))
    audit_corpus(tmp_path)

    path.unlink()
    gone = audit_corpus(tmp_path)
    assert [r["file"] for r in gone.removed] == ["216763.pdf"]
    assert gone.removed[0]["chemical_name"] == "Hydrogen peroxide solution"
    assert audit_corpus(tmp_path).removed == []  # not re-reported

    path.write_bytes(_pdf(_H2O2))
    assert audit_corpus(tmp_path).documents[0].status == NEW
    events = _events(tmp_path / ".ingestion_audit.jsonl")
    assert [e["event"] for e in events] == [NEW, REMOVED, NEW]


def test_byte_identical_copies_are_flagged(tmp_path):
    (tmp_path / "a.pdf").write_bytes(_pdf(_H2O2))
    (tmp_path / "b.pdf").write_bytes(_pdf(_H2O2))

    report = audit_corpus(tmp_path)

    assert report.duplicates == [["a.pdf", "b.pdf"]]
    assert all(any("byte-identical" in f for f in d.findings) for d in report.documents)


def test_dry_run_writes_nothing(tmp_path):
    (tmp_path / "216763.pdf").write_bytes(_pdf(_H2O2))

    report = audit_corpus(tmp_path, write=False)

    assert report.documents[0].status == NEW
    assert report.events_written == 0
    assert not (tmp_path / ".ingestion_audit.jsonl").exists()


def test_unreadable_pdf_is_reported_not_fatal(tmp_path):
    (tmp_path / "broken.pdf").write_bytes(b"%PDF-1.4\nnot really a pdf")
    (tmp_path / "216763.pdf").write_bytes(_pdf(_H2O2))

    report = audit_corpus(tmp_path)

    broken = next(d for d in report.documents if d.file == "broken.pdf")
    assert any("could not be read" in f for f in broken.findings)
    assert next(d for d in report.documents if d.file == "216763.pdf").chemical_name


def test_report_text_lists_every_document(tmp_path):
    (tmp_path / "216763.pdf").write_bytes(_pdf(_H2O2))
    text = format_report(audit_corpus(tmp_path, write=False))
    assert "216763.pdf" in text and "Hydrogen peroxide solution" in text
