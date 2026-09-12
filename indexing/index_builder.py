"""Index builder — constructs all three indexes from ProcessedDocuments (M1).

This is the orchestrator that takes a list of fully extracted and preprocessed
documents and feeds them into the inverted, positional, and k-gram indexes.

It also handles the preprocessing step: for each document, it runs the text
through the preprocessing pipeline (tokenize → stop words → selective stem)
and stores the resulting tokens back into the ProcessedDocument.

Usage:
    from indexing.index_builder import build_all_indexes
    inverted, positional, kgram = build_all_indexes(documents)
"""

from __future__ import annotations

from extraction.models import ProcessedDocument
from indexing.inverted_index import InvertedIndex
from indexing.kgram_index import KGramIndex
from indexing.positional_index import PositionalIndex
from preprocessing.pipeline import preprocess


def build_all_indexes(
    documents: list[ProcessedDocument],
) -> tuple[InvertedIndex, PositionalIndex, KGramIndex]:
    """Build all three indexes from a list of ProcessedDocuments.

    Steps:
        1. For each document, preprocess its section text into tokens.
        2. Store tokens back into the ProcessedDocument.
        3. Feed tokens into the inverted index (Lab 03).
        4. Feed tokens into the positional index (Lab 03).
        5. Build the k-gram index from the combined vocabulary (Lab 04).

    Args:
        documents: List of ProcessedDocument (from extraction pipeline).
                   The tokens field will be populated in-place.

    Returns:
        Tuple of (InvertedIndex, PositionalIndex, KGramIndex).
    """
    inverted = InvertedIndex()
    positional = PositionalIndex()

    for doc in documents:
        doc_id = doc.metadata.document_id

        # Combine all section text for preprocessing.
        # We prepend the chemical name so it's always in the token stream.
        full_text_parts = [doc.metadata.chemical_name]
        if doc.metadata.cas_number:
            full_text_parts.append(doc.metadata.cas_number)

        for _sec_num in sorted(doc.sections.keys()):
            full_text_parts.append(doc.sections[_sec_num])

        full_text = " ".join(full_text_parts)

        # Preprocess the text.
        tokens = preprocess(full_text)
        doc.tokens = tokens

        # Feed into indexes.
        inverted.add_document(doc_id, tokens)
        positional.add_document(doc_id, tokens)

    # Build k-gram index from the combined vocabulary of the inverted index.
    kgram = KGramIndex(k=3)
    kgram.build(inverted.vocabulary)

    return inverted, positional, kgram


def add_document_to_indexes(
    doc: ProcessedDocument,
    inverted: InvertedIndex,
    positional: PositionalIndex,
    kgram: KGramIndex,
) -> None:
    """Add a single new document to existing indexes (incremental update).

    Use this when a new SDS is crawled and needs to be indexed without
    rebuilding everything from scratch.

    Args:
        doc: The new ProcessedDocument to add.
        inverted: Existing inverted index to update.
        positional: Existing positional index to update.
        kgram: Existing k-gram index to update.
    """
    doc_id = doc.metadata.document_id

    # Preprocess if tokens are empty.
    if not doc.tokens:
        full_text_parts = [doc.metadata.chemical_name]
        if doc.metadata.cas_number:
            full_text_parts.append(doc.metadata.cas_number)
        for _sec_num in sorted(doc.sections.keys()):
            full_text_parts.append(doc.sections[_sec_num])
        doc.tokens = preprocess(" ".join(full_text_parts))

    inverted.add_document(doc_id, doc.tokens)
    positional.add_document(doc_id, doc.tokens)

    # Add any new terms to the k-gram index.
    for token in set(doc.tokens):
        if token not in kgram.vocabulary:
            kgram.add_term(token)
