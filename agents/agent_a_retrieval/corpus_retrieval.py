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

Why thresholds require an exact name match while typo tolerance only
*suggests*: the Lab 04 cascade measures spelling similarity, not chemical
identity. On the real corpus it resolved "Methanol" and "Ethanolamine" to
Ethanol, and "Hydroquinone" and "Hydrazine" to Hydrogen peroxide solution,
so those chemicals were silently evaluated against another substance's
storage limits. A threshold borrowed from a different SDS is worse than no
threshold: it produces a confident SAFE/WARNING with a real-looking
citation, where the honest answer is UNKNOWN. So `get_thresholds` fails
closed on anything but the chemical's own SDS, and `resolve_name` keeps the
cascade available as a "did you mean ...?" that a person must confirm by
searching the suggested name.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from agents.agent_a_retrieval.kgram_index import KGramIndex
from agents.agent_a_retrieval.provenance_bridge import convert_all
from agents.agent_a_retrieval.source_authority import rank_by_authority
from agents.agent_a_retrieval.tolerant_match import MatchResult, resolve
from agents.protocols.schemas import ProvenancedThreshold
from extraction.models import ProcessedDocument
from extraction.pipeline import extract_document


def _normalize_name(name: str) -> str:
    """Fold differences in a chemical name that never change which substance it is.

    Only case and whitespace are folded. Anything that could distinguish
    two substances -- hyphens, locants, digits, "solution" -- is kept, so
    "2 Propanol" is a suggestion for "2-Propanol", never a silent match.
    """
    return " ".join(name.split()).lower()


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
        # Normalized key -> name as the SDS spells it, so a suggestion reads
        # "Hydrogen peroxide solution" rather than the lowercased index key.
        self._display_names: dict[str, str] = {}
        for document in documents:
            key = _normalize_name(document.metadata.chemical_name)
            self._documents_by_chemical[key].append(document)
            self._display_names.setdefault(key, document.metadata.chemical_name)

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

    def resolve_name(self, chemical_query: str) -> MatchResult | None:
        """Find the corpus chemical a (possibly misspelled) query most likely means.

        Runs the Lab 04 tolerant-matching cascade (exact -> k-gram/edit
        distance -> Soundex). The result is a *suggestion* for a person to
        confirm, never a substitution: `get_thresholds` does not use it (see
        module docstring for the real-corpus cases where the closest
        spelling was a different chemical).

        Args:
            chemical_query: Chemical name as typed by an operator.

        Returns:
            The best match, with `term` set to the name as the SDS spells it
            and `stage`/`distance` saying how loose the match was, so the
            caller can tell an exact hit from a guess. None if nothing in
            the corpus is close.
        """
        matches = resolve(
            _normalize_name(chemical_query), self._vocabulary, self._kgram_index
        )
        if not matches:
            return None
        best = matches[0]
        return MatchResult(
            term=self._display_names[best.term],
            stage=best.stage,
            distance=best.distance,
        )

    def get_thresholds(self, chemical_query: str) -> list[ProvenancedThreshold]:
        """Retrieve cited thresholds from the queried chemical's own SDS only.

        Exact match after folding case and whitespace -- deliberately not
        the tolerant cascade. Every safety path (zone monitor,
        /safety/evaluate, the LLM's lookup tool) reaches thresholds through
        here, and a near-miss name is a different substance whose limits
        must not be borrowed. A miss returns [] so the state machine
        reports UNKNOWN; callers with a person in the loop can offer
        `resolve_name` as a suggestion.

        Args:
            chemical_query: Chemical name as stored in the zone inventory
                or typed by an operator.

        Returns:
            ProvenancedThreshold list from every document for that chemical,
            ordered by the source authority hierarchy (plan §7) so the
            preferred source for each metric sorts first -- more than one if
            the corpus holds multiple suppliers' SDS for it (see module
            docstring). Empty if the corpus has no SDS under that name.
        """
        documents = self._documents_by_chemical.get(_normalize_name(chemical_query), [])

        thresholds: list[ProvenancedThreshold] = []
        for document in documents:
            thresholds.extend(convert_all(document.extractions))
        return rank_by_authority(thresholds)
