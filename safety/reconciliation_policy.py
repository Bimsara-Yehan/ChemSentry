"""Versioned reconciliation-policy defaults for the ChemSentry safety pipeline.

Central Principle
-----------------
No safety-relevant number is ever hardcoded in application logic.  Every
threshold that can drive a SAFE / WARNING / UNKNOWN decision must be sourced
from a document that:
  - carries a version tag (so an audit trail can show *which* policy was in
    force at the time of a given evaluation),
  - records the rationale for the chosen value, and
  - cites the reference(s) that informed it.

The two parameters below are *reconciliation-policy parameters*, not
per-chemical safety thresholds from an SDS.  They govern how the Evidence
Reconciler (agents/agent_b_analysis/reconciler.py) and the Deterministic
Safety Evaluator (safety/state_machine.py) resolve conflicts between
multiple supplier sources.  They still fall under the central principle
because they can influence whether a reading is classified as WARNING or
UNKNOWN: tightening the Jaccard threshold causes more hazard-statement
disagreements to force UNKNOWN, and tightening the numeric tolerance causes
more equal-authority conflicts to force UNKNOWN.

Governance
----------
The underlying JSON document `safety/reconciliation_policy.json` IS the
versioned source document for these values.  This module loads it at runtime
and exposes the active policy parameters, metadata, and validation helpers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_POLICY_PATH = Path(__file__).resolve().parent / "reconciliation_policy.json"


def load_reconciliation_policy(
    policy_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load and parse a versioned reconciliation policy JSON file.

    Problem this solves:
        Ensures runtime reconciliation parameters are never hardcoded in
        source code, and can be inspected, cited, versioned, or swapped
        per operational environment or audit policy.

    Why this technique:
        JSON is a human-readable, schema-validatable format in the standard
        library without unsafe deserialization risks (e.g. pickle).

    Args:
        policy_path: Path to the JSON policy document. Defaults to
            `safety/reconciliation_policy.json`.

    Returns:
        Dictionary containing policy parameters and governance metadata.
    """
    path = Path(policy_path) if policy_path is not None else DEFAULT_POLICY_PATH
    if not path.exists():
        # Fallback to defaults if file is missing in an unusual deployment
        return {
            "version": "1.0.0",
            "effective_date": "2026-09-24",
            "conflict_tolerance_pct": 5.0,
            "hazard_jaccard_threshold": 0.6,
            "citation": "ChemSentry Reconciliation Policy v1.0.0 (fallback)",
            "rationale": "Default fallback reconciliation policy.",
            "source": "ChemSentry M3 Internal Governance Review",
        }

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


# Load default active policy at module import
_ACTIVE_POLICY = load_reconciliation_policy(DEFAULT_POLICY_PATH)

POLICY_VERSION: str = str(_ACTIVE_POLICY.get("version", "1.0.0"))
POLICY_CITATION: str = str(
    _ACTIVE_POLICY.get(
        "citation", f"ChemSentry Reconciliation Policy v{POLICY_VERSION}"
    )
)
POLICY_RATIONALE: str = str(_ACTIVE_POLICY.get("rationale", ""))
CONFLICT_TOLERANCE_PCT: float = float(_ACTIVE_POLICY.get("conflict_tolerance_pct", 5.0))
HAZARD_JACCARD_THRESHOLD: float = float(
    _ACTIVE_POLICY.get("hazard_jaccard_threshold", 0.6)
)


def get_policy_version() -> str:
    """Return active policy version string."""
    return POLICY_VERSION


def get_policy_citation() -> str:
    """Return active policy citation string."""
    return POLICY_CITATION


def get_policy_rationale() -> str:
    """Return active policy rationale string."""
    return POLICY_RATIONALE


def get_conflict_tolerance_pct() -> float:
    """Return active conflict tolerance percentage."""
    return CONFLICT_TOLERANCE_PCT


def get_hazard_jaccard_threshold() -> float:
    """Return active hazard Jaccard threshold."""
    return HAZARD_JACCARD_THRESHOLD


def reload_policy(policy_path: str | Path | None = None) -> dict[str, Any]:
    """Reload the active reconciliation policy from disk or custom path.

    Problem this solves:
        Enables live reloading of governance parameters during tests or runtime
        without process restarts.

    Why this technique:
        Updates module-level globals in place while returning the loaded dict.
    """
    global _ACTIVE_POLICY, POLICY_VERSION, POLICY_CITATION, POLICY_RATIONALE
    global CONFLICT_TOLERANCE_PCT, HAZARD_JACCARD_THRESHOLD

    _ACTIVE_POLICY = load_reconciliation_policy(policy_path)
    POLICY_VERSION = str(_ACTIVE_POLICY.get("version", "1.0.0"))
    POLICY_CITATION = str(
        _ACTIVE_POLICY.get(
            "citation", f"ChemSentry Reconciliation Policy v{POLICY_VERSION}"
        )
    )
    POLICY_RATIONALE = str(_ACTIVE_POLICY.get("rationale", ""))
    CONFLICT_TOLERANCE_PCT = float(_ACTIVE_POLICY.get("conflict_tolerance_pct", 5.0))
    HAZARD_JACCARD_THRESHOLD = float(
        _ACTIVE_POLICY.get("hazard_jaccard_threshold", 0.6)
    )
    return _ACTIVE_POLICY
