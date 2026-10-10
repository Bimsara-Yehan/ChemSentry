"""Corpus ingestion audit: what entered the SDS corpus, and what was read from it (M1).

Problem solved: SDS PDFs reach `corpus/raw/` from several places -- the
crawler, the admin upload route, or a teammate copying files in by hand --
and the moment they are there they start driving safety decisions. Nothing
recorded *which* documents were in the corpus at a given time, whether a
file was silently replaced by a different revision, or what the extraction
pipeline actually managed to read from each one. A safety officer asking
"why did Ethanol become SAFE/WARNING on Tuesday?" had no trail back to the
document that changed it.

This module is that trail. Each run:
    1. fingerprints every PDF in the corpus (SHA-256 of the bytes),
    2. runs it through the real loader + extraction pipeline -- the same code
       the API uses -- and records what came out (Section 1 metadata, which
       GHS sections were found, every extracted claim type, the storage-
       temperature limits with their source text),
    3. compares against the previous run's log to classify each file as
       NEW, CHANGED (same name, different PDF bytes or a different admin
       override sidecar), UNCHANGED or REMOVED, and
       flags byte-identical DUPLICATES under different names,
    4. appends one event per new / changed / removed file to an append-only
       JSON Lines log, so history is never rewritten.

Nothing is hardcoded: every recorded value is read from the document or
produced by the extraction pipeline, and every finding is a test on that
output (e.g. "Section 1 gave no chemical name"), never a judgement about a
particular chemical. Why JSON Lines and not a database table: the corpus
layer has no database dependency, one line per event is append-only by
construction, and it diffs cleanly; the API's own audit table (M4) is a
separate, complementary record of user actions.

Usage (from the repository root):
    python -m corpus.ingestion_audit                 # audit corpus/raw, append events
    python -m corpus.ingestion_audit --dry-run       # report only, write nothing
    python -m corpus.ingestion_audit --json          # machine-readable report
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from corpus.pdf_loader import load_sds_pdf, override_path_for
from extraction.models import ClaimType, ProcessedDocument
from extraction.pipeline import extract_document

DEFAULT_RAW_DIR = Path(__file__).resolve().parent / "raw"
# Lives inside corpus/raw/, which .gitignore already excludes, so a machine's
# local corpus history is never committed alongside the code.
DEFAULT_LOG_NAME = ".ingestion_audit.jsonl"

NEW, CHANGED, UNCHANGED, REMOVED = "new", "changed", "unchanged", "removed"

# Claim types that become storage-temperature thresholds downstream -- the
# values that actually move a zone between SAFE / WARNING / UNKNOWN.
_STORAGE_CLAIMS = (ClaimType.STORAGE_TEMP_MIN, ClaimType.STORAGE_TEMP_MAX)
# The GHS section storage limits are extracted from (section_splitter.py).
_STORAGE_SECTION = 7
# Placeholder pdf_loader uses when Section 1 yields no value.
_UNPARSED = "unknown"


def sha256_of(path: Path) -> str:
    """Hex SHA-256 of a file's bytes.

    Why a content hash rather than size/mtime: a replaced SDS revision can
    have the same name and a similar size, and copying a file resets mtime;
    only the bytes identify which document was actually in the corpus.
    """
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class DocumentRecord:
    """What the pipeline read from one SDS file."""

    file: str
    document_id: str
    sha256: str
    status: str = UNCHANGED
    chemical_name: str | None = None
    supplier: str | None = None
    cas_number: str | None = None
    sds_version: str | None = None
    revision_date: str | None = None
    overrides_applied: bool = False
    # Hash of the admin override sidecar (<id>.meta.json), if any. Part of the
    # fingerprint because an override changes the chemical name / supplier
    # the system uses without touching the PDF bytes.
    overrides_sha256: str | None = None
    sections_found: list[int] = field(default_factory=list)
    claim_counts: dict[str, int] = field(default_factory=dict)
    storage_limits: list[dict] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    previous_sha256: str | None = None
    previous_overrides_sha256: str | None = None
    # What changed since the last run: "pdf" and/or "overrides".
    changed: list[str] = field(default_factory=list)


def _findings(doc: ProcessedDocument) -> list[str]:
    """Data-quality checks on the extraction output.

    Each finding is derived from what the pipeline returned for this file,
    so it explains why a chemical might report UNKNOWN downstream (for
    example, no Section 7 means no storage limit can ever be extracted).
    """
    meta = doc.metadata
    found = []
    if meta.chemical_name == _UNPARSED:
        found.append(
            "Section 1 gave no chemical name; retrieval cannot match this SDS by name"
        )
    if meta.supplier == _UNPARSED:
        found.append("Section 1 gave no supplier; citations will read 'unknown'")
    if not meta.cas_number:
        found.append("no CAS number parsed from Section 1")
    if not doc.sections:
        found.append(
            "no GHS sections recognised; the PDF may be scanned or use a non-standard layout"
        )
    elif _STORAGE_SECTION not in doc.sections:
        found.append(f"Section {_STORAGE_SECTION} (handling and storage) not found")
    if not any(e.claim_type in _STORAGE_CLAIMS for e in doc.extractions):
        found.append(
            "no storage-temperature limit extracted; zones storing this chemical stay UNKNOWN"
        )
    return found


def inspect_document(path: Path) -> DocumentRecord:
    """Fingerprint one PDF and record what the real pipeline extracts from it."""
    sidecar = override_path_for(path)
    record = DocumentRecord(
        file=path.name,
        document_id=path.stem,
        sha256=sha256_of(path),
        overrides_sha256=sha256_of(sidecar) if sidecar.is_file() else None,
    )
    try:
        raw_text, metadata = load_sds_pdf(path)
        doc = extract_document(raw_text, metadata)
    except (
        Exception
    ) as exc:  # noqa: BLE001 -- a bad PDF must be reported, not crash the audit
        record.findings.append(
            f"could not be read or extracted: {type(exc).__name__}: {exc}"
        )
        return record

    meta = doc.metadata
    record.document_id = meta.document_id
    record.chemical_name = meta.chemical_name
    record.supplier = meta.supplier
    record.cas_number = meta.cas_number
    record.sds_version = meta.sds_version
    record.revision_date = (
        meta.revision_date.isoformat() if meta.revision_date else None
    )
    record.overrides_applied = record.overrides_sha256 is not None
    record.sections_found = sorted(doc.sections)
    record.claim_counts = dict(
        sorted(Counter(e.claim_type.value for e in doc.extractions).items())
    )
    record.storage_limits = [
        {
            "claim": e.claim_type.value,
            "value": e.value,
            "unit": e.unit,
            "section": e.section_number,
            "source_text": e.original_text_span.strip(),
        }
        for e in doc.extractions
        if e.claim_type in _STORAGE_CLAIMS
    ]
    record.findings = _findings(doc)
    return record


def _last_events(log_path: Path) -> dict[str, dict]:
    """Latest logged event per file name, replaying the append-only log."""
    latest: dict[str, dict] = {}
    if not log_path.is_file():
        return latest
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # a torn line must not hide the rest of the history
        if isinstance(event, dict) and "file" in event:
            latest[event["file"]] = event
    return latest


@dataclass
class AuditReport:
    """Result of one audit run."""

    raw_dir: str
    audited_at: str
    documents: list[DocumentRecord]
    removed: list[dict]
    duplicates: list[list[str]]
    events_written: int

    def counts(self) -> dict[str, int]:
        counted = Counter(d.status for d in self.documents)
        counted[REMOVED] = len(self.removed)
        return {k: counted.get(k, 0) for k in (NEW, CHANGED, UNCHANGED, REMOVED)}


def audit_corpus(
    raw_dir: Path = DEFAULT_RAW_DIR,
    log_path: Path | None = None,
    *,
    actor: str = "system",
    write: bool = True,
    now: datetime | None = None,
) -> AuditReport:
    """Audit every SDS PDF in `raw_dir` against the previous audit log.

    Args:
        raw_dir: Corpus directory (default `corpus/raw/`).
        log_path: Append-only JSON Lines log (default `<raw_dir>/.ingestion_audit.jsonl`).
        actor: Who triggered the run, recorded on each event.
        write: False for a dry run (report only).
        now: Timestamp override, for tests.

    Returns:
        AuditReport with one DocumentRecord per PDF, files that disappeared
        since the last run, byte-identical duplicates, and how many events
        were appended.
    """
    raw_dir = Path(raw_dir)
    log_path = Path(log_path) if log_path else raw_dir / DEFAULT_LOG_NAME
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    previous = _last_events(log_path)

    documents = []
    for path in sorted(raw_dir.glob("*.pdf")):
        record = inspect_document(path)
        prior = previous.get(record.file)
        if prior is None or prior.get("event") == REMOVED:
            record.status = NEW
        else:
            if prior.get("sha256") != record.sha256:
                record.changed.append("pdf")
                record.previous_sha256 = prior.get("sha256")
            if prior.get("overrides_sha256") != record.overrides_sha256:
                record.changed.append("overrides")
                record.previous_overrides_sha256 = prior.get("overrides_sha256")
            if record.changed:
                record.status = CHANGED
        documents.append(record)

    present = {d.file for d in documents}
    removed = [
        {
            "file": name,
            "sha256": event.get("sha256"),
            "chemical_name": event.get("chemical_name"),
        }
        for name, event in sorted(previous.items())
        if name not in present and event.get("event") != REMOVED
    ]

    by_hash: dict[str, list[str]] = {}
    for d in documents:
        by_hash.setdefault(d.sha256, []).append(d.file)
    duplicates = [names for names in by_hash.values() if len(names) > 1]
    for d in documents:
        twins = [n for n in by_hash[d.sha256] if n != d.file]
        if twins:
            d.findings.append(
                f"byte-identical to {', '.join(twins)}; the corpus holds this SDS twice"
            )

    events = [
        {"event": d.status, "at": stamp, "actor": actor, **asdict(d)}
        for d in documents
        if d.status in (NEW, CHANGED)
    ] + [{"event": REMOVED, "at": stamp, "actor": actor, **r} for r in removed]

    if write and events:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:  # append-only
            for event in events:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    return AuditReport(
        raw_dir=str(raw_dir),
        audited_at=stamp,
        documents=documents,
        removed=removed,
        duplicates=duplicates,
        events_written=len(events) if write else 0,
    )


def format_report(report: AuditReport) -> str:
    """Human-readable summary for the terminal."""
    lines = [f"SDS corpus audit | {report.raw_dir} | {report.audited_at}"]
    counts = report.counts()
    lines.append("  " + "  ".join(f"{k}: {v}" for k, v in counts.items()))
    if not report.documents and not report.removed:
        lines.append("  No SDS PDFs found.")
    for d in report.documents:
        limits = ", ".join(
            f"{s['claim'].replace('storage_temperature_', '')} {s['value']} {s['unit']}".strip()
            for s in d.storage_limits
        )
        lines.append("")
        lines.append(f"[{d.status.upper()}] {d.file}  sha256 {d.sha256[:12]}")
        lines.append(
            f"  chemical: {d.chemical_name}  supplier: {d.supplier}  CAS: {d.cas_number or '-'}"
        )
        lines.append(
            f"  sections: {d.sections_found or '-'}  claims: {sum(d.claim_counts.values())}  storage limits: {limits or 'none'}"
        )
        if d.changed:
            lines.append(f"  changed: {', '.join(d.changed)}")
        if d.overrides_applied:
            lines.append("  admin overrides applied from .meta.json")
        for f in d.findings:
            lines.append(f"  ! {f}")
    for r in report.removed:
        lines.append("")
        lines.append(f"[REMOVED] {r['file']}  ({r.get('chemical_name') or 'unknown'})")
    lines.append("")
    lines.append(f"{report.events_written} event(s) appended to the audit log.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the SDS corpus (corpus/raw/).")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument(
        "--log", type=Path, default=None, help="Audit log path (JSON Lines)."
    )
    parser.add_argument("--actor", default="system", help="Who is running the audit.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Report only; append nothing."
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    args = parser.parse_args()

    report = audit_corpus(
        args.raw_dir, args.log, actor=args.actor, write=not args.dry_run
    )
    if args.json:
        print(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    else:
        print(format_report(report))


if __name__ == "__main__":
    main()
