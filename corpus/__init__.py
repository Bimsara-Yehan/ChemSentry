"""SDS document acquisition (M1).

Two acquisition paths feed the same downstream extraction pipeline:
    corpus.crawler    — fetches SDS PDFs from the web (frontier, robots.txt,
                         politeness delay). Not yet implemented.
    corpus.pdf_loader — loads SDS PDFs already on disk (corpus/raw/) and
                         extracts their text + minimal Section 1 metadata.
"""
