"""Real Agent A retrieval entry point: chemical name -> cited thresholds (M2).

Ties together pieces built this session that nothing in the live app calls
yet: `corpus.pdf_loader` (PDF -> text + metadata), `extraction.pipeline`
(text -> ExtractionResult with full provenance), `tolerant_match` +
`KGramIndex` (typo-tolerant chemical-name resolution, Lab 04), and
`provenance_bridge` (ExtractionResult -> ProvenancedThreshold). This is what
`api/main.py` needs to call instead of
`MOCK_SDS_DATABASE_PENDING_AGENT_A_RETRIEVAL` -- see that constant's own
comment for why swapping it in is what makes "no threshold is hardcoded"
true end-to-end, not just true inside the unwired extraction layer.

Why one chemical name can legitimately resolve to thresholds from *multiple*
documents: the corpus can hold more than one supplier's SDS for the same
substance -- this project's own corpus/raw/ has exactly that for sulfuric
acid. That is not a bug to collapse away here; it is precisely the
conflicting-evidence case `agents/agent_b_analysis/reconciler.py` and
`safety/state_machine.py` already know how to resolve. This module's job
stops at retrieving and citing evidence -- it never picks a winner between
sources, that's the reconciler's job.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from agents.agent_a_retrieval.kgram_index import KGramIndex
from agents.agent_a_retrieval.provenance_bridge import convert_all
from agents.agent_a_retrieval.source_authority import rank_by_authority
from agents.agent_a_retrieval.tolerant_match import resolve
from agents.protocols.schemas import ProvenancedThreshold
from extraction.models import ProcessedDocument
from extraction.pipeline import extract_document


class CorpusRetriever:
    """Resolves chemical-name queries against a set of processed SDS documents.

    Constructed from already-extracted `ProcessedDocument`s (see
    `from_local_pdfs` for the convenience path that does the PDF loading and
    extraction itself) so unit tests can exercise the resolution logic with
    small synthetic documents, without depending on real PDF files.
    """

    def __init__(self, documents: list[ProcessedDocument]) -> None:
        """
        Args:
            documents: Already-extracted SDS documents (chemical name,
                sections, and extractions all populated).
        """
        self._documents_by_chemical: dict[str, list[ProcessedDocument]] = defaultdict(
            list
        )
        for document in documents:
            key = document.metadata.chemical_name.lower()
            self._documents_by_chemical[key].append(document)

        self._vocabulary = list(self._documents_by_chemical.keys())
        self._kgram_index = KGramIndex(self._vocabulary)

    @classmethod
    def from_local_pdfs(cls, raw_dir: Path) -> "CorpusRetriever":
        """Build a retriever from every PDF in a local directory (corpus/raw/).

        Args:
            raw_dir: Directory of local SDS PDFs.
        """
        from corpus.pdf_loader import load_all_local_pdfs

        documents = [
            extract_document(raw_text, metadata)
            for raw_text, metadata in load_all_local_pdfs(raw_dir)
        ]
        return cls(documents)

    @property
    def vocabulary(self) -> list[str]:
        """Real chemical names this corpus can resolve queries against.

        Not a replacement for `agents/agent_a_retrieval/vocabulary.py`'s
        placeholder list -- that file is a deliberately fixed test fixture
        the existing M2 test suite is hand-curated against (see its own
        docstring). This is the real, corpus-derived equivalent for
        production use.
        """
        return list(self._vocabulary)

    def get_thresholds(self, chemical_query: str) -> list[ProvenancedThreshold]:
        """Resolve a (possibly misspelled) chemical name to cited thresholds.

        Args:
            chemical_query: Chemical name as typed by an operator or agent --
                may contain typos, resolved via the Lab 04 tolerant-matching
                cascade (exact -> k-gram/edit-distance -> Soundex).

        Returns:
            ProvenancedThreshold list from every document matching the
            resolved chemical name, ordered by the source authority
            hierarchy (plan §7) so the preferred source for each metric
            sorts first -- more than one if the corpus holds multiple
            suppliers' SDS for it (see module docstring). Empty if the
            query doesn't resolve to anything in this corpus.
        """
        matches = resolve(chemical_query, self._vocabulary, self._kgram_index)
        if not matches:
            return []

        resolved_name = matches[0].term
        documents = self._documents_by_chemical.get(resolved_name, [])

        thresholds: list[ProvenancedThreshold] = []
        for document in documents:
            thresholds.extend(convert_all(document.extractions))
        return rank_by_authority(thresholds)
