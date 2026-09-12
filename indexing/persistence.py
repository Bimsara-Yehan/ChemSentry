"""Index persistence — save and load indexes to/from disk (M1).

Uses JSON for human-readable, debuggable persistence during development.
JSON is slower than pickle but safer (no arbitrary code execution on load)
and easier to inspect when debugging retrieval issues.

Usage:
    from indexing.persistence import save_indexes, load_indexes

    save_indexes("indexes/", inverted, positional, kgram)
    inverted, positional, kgram = load_indexes("indexes/")
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from indexing.inverted_index import InvertedIndex
from indexing.kgram_index import KGramIndex
from indexing.positional_index import PositionalIndex

# Default filenames within the index directory.
_INVERTED_FILE = "inverted_index.json"
_POSITIONAL_FILE = "positional_index.json"
_KGRAM_FILE = "kgram_index.json"


def save_indexes(
    directory: str | Path,
    inverted: InvertedIndex,
    positional: PositionalIndex,
    kgram: KGramIndex,
) -> None:
    """Save all three indexes to a directory as JSON files.

    Creates the directory if it doesn't exist.

    Args:
        directory: Path to the directory where index files will be saved.
        inverted: InvertedIndex to save.
        positional: PositionalIndex to save.
        kgram: KGramIndex to save.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    with open(directory / _INVERTED_FILE, "w", encoding="utf-8") as f:
        json.dump(inverted.to_dict(), f, ensure_ascii=False, indent=2)

    with open(directory / _POSITIONAL_FILE, "w", encoding="utf-8") as f:
        json.dump(positional.to_dict(), f, ensure_ascii=False, indent=2)

    with open(directory / _KGRAM_FILE, "w", encoding="utf-8") as f:
        json.dump(kgram.to_dict(), f, ensure_ascii=False, indent=2)


def load_indexes(
    directory: str | Path,
) -> tuple[InvertedIndex, PositionalIndex, KGramIndex]:
    """Load all three indexes from a directory.

    Args:
        directory: Path to the directory containing index JSON files.

    Returns:
        Tuple of (InvertedIndex, PositionalIndex, KGramIndex).

    Raises:
        FileNotFoundError: If any index file is missing.
    """
    directory = Path(directory)

    with open(directory / _INVERTED_FILE, "r", encoding="utf-8") as f:
        inverted = InvertedIndex.from_dict(json.load(f))

    with open(directory / _POSITIONAL_FILE, "r", encoding="utf-8") as f:
        positional = PositionalIndex.from_dict(json.load(f))

    with open(directory / _KGRAM_FILE, "r", encoding="utf-8") as f:
        kgram = KGramIndex.from_dict(json.load(f))

    return inverted, positional, kgram


def indexes_exist(directory: str | Path) -> bool:
    """Check if all three index files exist in the directory.

    Args:
        directory: Path to check.

    Returns:
        True if all three index files exist.
    """
    directory = Path(directory)
    return all(
        (directory / f).exists()
        for f in [_INVERTED_FILE, _POSITIONAL_FILE, _KGRAM_FILE]
    )
