"""Full extraction pipeline orchestrator (M1, Lab 07).

Processes a single SDS document through the complete extraction pipeline:
    1. Split raw text into GHS sections (section_splitter)
    2. Extract values from each section (value_extractor)
    3. Normalise units (normaliser)
    4. Attach provenance metadata (models)
    5. Return a ProcessedDocument ready for indexing

This is the single entry point that the indexing layer and the crawler call.

Usage:
    from extraction.pipeline import extract_document
    doc = extract_document(raw_text, metadata)
    print(doc.extractions)  # list of ExtractionResult with provenance
"""

from __future__ import annotations

from extraction.models import (
    ExtractionResult,
    ProcessedDocument,
    SDSMetadata,
)
from extraction.normaliser import normalise_value
from extraction.section_splitter import split_sections
from extraction.value_extractor import extract_all_from_section


def extract_document(
    raw_text: str,
    metadata: SDSMetadata,
) -> ProcessedDocument:
    """Run the full extraction pipeline on a single SDS document.

    Args:
        raw_text: Full text of the SDS (from PDF extraction or HTML).
        metadata: Document-level metadata (chemical, supplier, version, etc.).

    Returns:
        ProcessedDocument with sections, extractions, and empty tokens
        (tokens are populated by the preprocessing pipeline, not here —
        separation of concerns between extraction and preprocessing).
    """
    # Step 1: Split into GHS sections.
    section_split = split_sections(raw_text)

    # Step 2 & 3: Extract values from each section with normalisation.
    all_extractions: list[ExtractionResult] = []

    # Build kwargs that carry provenance through to every ExtractionResult.
    provenance_kwargs = {
        "document_id": metadata.document_id,
        "supplier": metadata.supplier,
        "sds_revision": metadata.sds_version,
        "revision_date": metadata.revision_date,
    }

    for section_num, section_text in section_split.sections.items():
        section_results = extract_all_from_section(
            text=section_text,
            section_number=section_num,
            chemical=metadata.chemical_name,
            **provenance_kwargs,
        )

        # Step 3: Normalise units on numeric extractions.
        for result in section_results:
            if result.unit and result.value.replace(".", "").isdigit():
                try:
                    normalised = normalise_value(
                        float(result.value), result.unit
                    )
                    # Update the result with normalised value if conversion
                    # was applied, but KEEP the original in the text span.
                    if normalised.conversion_applied != "no conversion applied":
                        result = result.model_copy(update={
                            "value": str(normalised.normalised_value),
                            "unit": normalised.normalised_unit,
                        })
                except (ValueError, TypeError):
                    pass  # Non-numeric value — skip normalisation.

            all_extractions.append(result)

    # Step 4: Build the ProcessedDocument.
    return ProcessedDocument(
        metadata=metadata,
        sections=section_split.sections,
        extractions=all_extractions,
        tokens=[],  # Populated by preprocessing.pipeline.preprocess() — not here.
    )
