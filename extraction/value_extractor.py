"""Regex-based value extraction from SDS sections (M1, Lab 07).

Extracts structured safety values from raw SDS section text:
    - Storage temperature limits (Section 7)
    - Humidity limits (Section 7)
    - CAS registry numbers (Section 3)
    - GHS H-codes and P-codes (Section 2)
    - Occupational exposure limits — TWA, STEL, PEL, TLV (Section 8)
    - PPE requirements (Section 8)
    - Flash point and boiling point (Section 9)
    - Incompatible materials (Section 10)

SECURITY (plan §17):
    All regexes use BOUNDED QUANTIFIERS ({0,N} instead of .*) and a
    configurable TIMEOUT to prevent ReDoS (catastrophic backtracking).
    Our regex layer is the primary extraction path — a hung regex hangs
    the entire pipeline.

Design decision:
    Each extraction function returns a list of ExtractionResult with full
    provenance (plan §9).  This means every value carries its source
    document, section, original text span, and confidence score all the
    way through to the final safety alert.
"""

from __future__ import annotations

import re
import signal
import sys

from extraction.models import (
    ClaimType,
    ExtractionMethod,
    ExtractionResult,
    SourceAuthority,
)

# ---------------------------------------------------------------------------
# Timeout mechanism for regex safety (ReDoS prevention)
# ---------------------------------------------------------------------------

# Default timeout in seconds for any single regex operation.
REGEX_TIMEOUT_SECONDS: int = 5


class RegexTimeoutError(Exception):
    """Raised when a regex operation exceeds the timeout."""

    pass


def _regex_findall_safe(
    pattern: re.Pattern[str],
    text: str,
    timeout: int = REGEX_TIMEOUT_SECONDS,
) -> list[re.Match[str]]:
    """Run re.finditer with a timeout to prevent ReDoS.

    On Windows, signal.SIGALRM is not available, so we fall back to
    running without a hard timeout but with bounded patterns.
    On Unix, uses SIGALRM for a hard time limit.

    Args:
        pattern: Compiled regex pattern (should use bounded quantifiers).
        text: Text to search.
        timeout: Maximum seconds to allow.

    Returns:
        List of Match objects found.

    Raises:
        RegexTimeoutError: If the regex exceeds the timeout (Unix only).
    """
    if sys.platform != "win32" and hasattr(signal, "SIGALRM"):

        def _handler(signum, frame):
            raise RegexTimeoutError(
                f"Regex timed out after {timeout}s on pattern {pattern.pattern!r}"
            )

        old_handler = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(timeout)
        try:
            results = list(pattern.finditer(text))
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    else:
        # Windows fallback — rely on bounded quantifiers in the patterns.
        # We truncate excessively long text as an additional safeguard.
        MAX_TEXT_LENGTH = 500_000  # 500 KB — generous for any single SDS
        results = list(pattern.finditer(text[:MAX_TEXT_LENGTH]))

    return results


# ---------------------------------------------------------------------------
# Extraction patterns — all use BOUNDED quantifiers
# ---------------------------------------------------------------------------

# Storage temperature maximum: "store below 25 °C", "keep under 30°C"
_STORAGE_TEMP_MAX_RE = re.compile(
    r"(?:store|keep|storage).{0,60}?"
    r"(?:below|under|not\s+(?:above|exceed)|max(?:imum)?|≤|<=)\s*"
    r"(\d+\.?\d*)\s*°?\s*([CF])",
    re.IGNORECASE,
)

# Storage temperature minimum: "store above 5 °C", "keep above freezing"
_STORAGE_TEMP_MIN_RE = re.compile(
    r"(?:store|keep|storage).{0,60}?"
    r"(?:above|over|min(?:imum)?|≥|>=)\s*"
    r"(\d+\.?\d*)\s*°?\s*([CF])",
    re.IGNORECASE,
)

# Label:value storage temperature range, e.g. real Sigma-Aldrich/GHS-EU SDS
# text: "Recommended storage temperature : 15 - 25 °C" (conventional layout)
# or, when a PDF's two-column label wraps across a line break, extracted as
# "Recommended storage : 15 - 25 °C\ntemperature" -- both forms confirmed
# against real SDS PDFs in corpus/raw/, not invented (see ADR pending).
# Captures an optional range (min, max) or a single ceiling value.
_STORAGE_TEMP_LABEL_RE = re.compile(
    r"storage(?:\s+temperature)?\s*:\s*"
    r"(-?\d+\.?\d*)\s*(?:[-–]\s*(-?\d+\.?\d*))?\s*°?\s*([CF])"
    r"(?:\s*\n\s*temperature\b)?",
    re.IGNORECASE,
)

# Humidity limits: "relative humidity below 60%"
_HUMIDITY_RE = re.compile(
    r"(?:humidity|RH|relative\s+humidity).{0,40}?"
    r"(?:below|under|not\s+exceed|max|≤|<=)?\s*"
    r"(\d+\.?\d*)\s*%",
    re.IGNORECASE,
)

# CAS registry numbers: 78-93-3, 1333-74-0
#
# Negative lookbehind excludes a CAS-shaped tail embedded inside a longer
# EU CLP Index-No. (format DDD-DDD-DD-D, e.g. "607-750-00-3"): confirmed
# against a real SDS PDF where this regex, without the lookbehind, extracted
# "750-00-3" out of the Index-No. and reported it as a second CAS number.
_CAS_RE = re.compile(r"(?<!\d{3}-)\b(\d{2,7}-\d{2}-\d)\b")

# H-codes: H301, H301+H311+H331
_H_CODE_RE = re.compile(r"\b(H\d{3}[A-Za-z]?(?:\s*\+\s*H\d{3}[A-Za-z]?)*)\b")

# P-codes: P280, P280+P310+P321
_P_CODE_RE = re.compile(r"\b(P\d{3}(?:\s*\+\s*P\d{3})*)\b")

# Exposure limits (TWA, STEL, PEL, TLV)
_EXPOSURE_RE = re.compile(
    r"(TWA|STEL|PEL|TLV|REL).{0,40}?" r"(\d+\.?\d*)\s*(mg/m[³3]|ppm|mg/m3)",
    re.IGNORECASE,
)

# PPE requirements: "wear nitrile gloves", "use safety goggles"
_PPE_RE = re.compile(
    r"(?:wear|use|required?|recommend).{0,80}?"
    r"((?:nitrile|rubber|latex|chemical[- ]resistant)?\s*"
    r"(?:gloves|goggles|glasses|respirator|mask|face\s*shield|"
    r"apron|boots|suit|protection))",
    re.IGNORECASE,
)

# Label:value PPE material, e.g. real Sigma-Aldrich/GHS-EU SDS Section 8
# text: "Hand protection\nMaterial : Nitrile rubber" -- confirmed against
# real SDS PDFs, where _PPE_RE above only ever matches the generic word
# "protection" on this vendor's label-formatted layout and misses the
# actual glove/eyewear material entirely.
_PPE_MATERIAL_RE = re.compile(
    r"Material\s*:\s*([A-Za-z][A-Za-z\-\s]{2,40}?)\s*(?:\n|$)",
    re.IGNORECASE,
)

# Flash point: "Flash point: 4 °C"
_FLASH_POINT_RE = re.compile(
    r"(?:flash\s*point).{0,30}?" r"(\d+\.?\d*)\s*°?\s*([CF])",
    re.IGNORECASE,
)

# Boiling point: "Boiling point: 111 °C"
_BOILING_POINT_RE = re.compile(
    r"(?:boiling\s*point).{0,30}?" r"(\d+\.?\d*)\s*°?\s*([CF])",
    re.IGNORECASE,
)

# Incompatible materials: "Incompatible with strong oxidizers, acids".
#
# Real SDS Section 10 text (confirmed against multiple real SDS PDFs, e.g.
# sodium hydroxide, hydrochloric acid) rarely uses the word "incompatible"
# at all -- it phrases the same claim as "Violent reactions possible with:",
# "can decompose violently in contact with:", or "Risk of ignition or
# formation of inflammable gases or vapours with:", each followed by a
# newline-separated list of substances rather than a single sentence.
# Shared between the trigger and the terminator: a real SDS Section 10 packs
# several of these sub-headings back to back with no period or blank line
# between them (confirmed: sodium hydroxide's Section 10 runs "Violent
# reactions possible with: <30+ substances> can decompose violently in
# contact with: ..." as one unbroken block), so the *next* trigger phrase is
# what actually ends the current one's list -- a bare length cap without this
# lookahead either runs the list together with the next hazard's list, or
# (if capped too short) fails to match at all when a real list has no period
# within the cap.
_INCOMPATIBILITY_TRIGGERS = (
    r"incompatible|incompatibility|avoid\s+contact|"
    r"violent\s+reactions?\s+possible|"
    r"can\s+decompose\s+violently\s+in\s+contact|"
    r"risk\s+of\s+ignition\s+or\s+formation\s+of\s+inflammable\s+gases?\s+or\s+vapours?|"
    r"risk\s+of\s+explosion"
)

_INCOMPATIBILITY_RE = re.compile(
    rf"(?:{_INCOMPATIBILITY_TRIGGERS})"
    r".{0,20}?(?:with\s*:?\s*)?"
    rf"(.{{5,400}}?)(?=\n\s*\n|\.|\n\s*(?:{_INCOMPATIBILITY_TRIGGERS})|\Z)",
    re.IGNORECASE | re.DOTALL,
)


# ---------------------------------------------------------------------------
# Extraction functions — one per claim type
# ---------------------------------------------------------------------------


def _make_result(
    chemical: str,
    claim_type: ClaimType,
    value: str,
    unit: str,
    section_number: int,
    original_text_span: str,
    confidence: float,
    document_id: str = "",
    supplier: str = "",
    sds_revision: str = "unknown",
    revision_date=None,
    source_authority: SourceAuthority = SourceAuthority.SUPPLIER_SDS,
) -> ExtractionResult:
    """Helper to build an ExtractionResult with consistent defaults."""
    return ExtractionResult(
        chemical=chemical,
        claim_type=claim_type,
        value=value,
        unit=unit,
        document_id=document_id,
        supplier=supplier,
        sds_revision=sds_revision,
        section_number=section_number,
        original_text_span=original_text_span[:200],  # cap span length
        extraction_method=ExtractionMethod.REGEX,
        confidence=confidence,
        source_authority=source_authority,
    )


def extract_storage_temp(
    text: str, section_number: int = 7, chemical: str = "", **kwargs
) -> list[ExtractionResult]:
    """Extract storage temperature limits from SDS text.

    Two source phrasings are matched, both confirmed against real supplier
    SDS PDFs (see corpus/raw/), not just imagined examples:
        - Sentence style:  "store below 25 °C", "keep under 30°C"
        - Label:value style, the dominant real-world format for at least one
          major supplier (Sigma-Aldrich/GHS-EU): "Recommended storage
          temperature : 15 - 25 °C". A two-column PDF layout can wrap this
          across a line break as "storage : 15 - 25 °C\\ntemperature" --
          the label regex tolerates both.

    Args:
        text: Raw section text (typically Section 7).
        section_number: GHS section number this text came from.
        chemical: Chemical name for provenance.

    Returns:
        List of ExtractionResult for any temperature limits found.
    """
    results: list[ExtractionResult] = []

    for match in _regex_findall_safe(_STORAGE_TEMP_MAX_RE, text):
        value = match.group(1)
        unit = f"°{match.group(2).upper()}"
        results.append(
            _make_result(
                chemical=chemical,
                claim_type=ClaimType.STORAGE_TEMP_MAX,
                value=value,
                unit=unit,
                section_number=section_number,
                original_text_span=match.group(0),
                confidence=0.90,
                **kwargs,
            )
        )

    for match in _regex_findall_safe(_STORAGE_TEMP_MIN_RE, text):
        value = match.group(1)
        unit = f"°{match.group(2).upper()}"
        results.append(
            _make_result(
                chemical=chemical,
                claim_type=ClaimType.STORAGE_TEMP_MIN,
                value=value,
                unit=unit,
                section_number=section_number,
                original_text_span=match.group(0),
                confidence=0.88,
                **kwargs,
            )
        )

    for match in _regex_findall_safe(_STORAGE_TEMP_LABEL_RE, text):
        low, high, unit_letter = match.group(1), match.group(2), match.group(3)
        unit = f"°{unit_letter.upper()}"

        if high is not None:
            # A range: "15 - 25 °C" -> min=15, max=25.
            results.append(
                _make_result(
                    chemical=chemical,
                    claim_type=ClaimType.STORAGE_TEMP_MIN,
                    value=low,
                    unit=unit,
                    section_number=section_number,
                    original_text_span=match.group(0),
                    confidence=0.85,
                    **kwargs,
                )
            )
            results.append(
                _make_result(
                    chemical=chemical,
                    claim_type=ClaimType.STORAGE_TEMP_MAX,
                    value=high,
                    unit=unit,
                    section_number=section_number,
                    original_text_span=match.group(0),
                    confidence=0.85,
                    **kwargs,
                )
            )
        else:
            # A single labelled value with no explicit direction word --
            # read as a ceiling, the conventional meaning of a bare storage
            # temperature figure on an SDS.
            results.append(
                _make_result(
                    chemical=chemical,
                    claim_type=ClaimType.STORAGE_TEMP_MAX,
                    value=low,
                    unit=unit,
                    section_number=section_number,
                    original_text_span=match.group(0),
                    confidence=0.75,
                    **kwargs,
                )
            )

    return results


def extract_humidity(
    text: str, section_number: int = 7, chemical: str = "", **kwargs
) -> list[ExtractionResult]:
    """Extract humidity limit from SDS text."""
    results: list[ExtractionResult] = []

    for match in _regex_findall_safe(_HUMIDITY_RE, text):
        results.append(
            _make_result(
                chemical=chemical,
                claim_type=ClaimType.STORAGE_HUMIDITY_MAX,
                value=match.group(1),
                unit="%",
                section_number=section_number,
                original_text_span=match.group(0),
                confidence=0.85,
                **kwargs,
            )
        )

    return results


def extract_cas_numbers(
    text: str, section_number: int = 3, chemical: str = "", **kwargs
) -> list[ExtractionResult]:
    """Extract CAS registry numbers from SDS text."""
    results: list[ExtractionResult] = []
    seen: set[str] = set()

    for match in _regex_findall_safe(_CAS_RE, text):
        cas = match.group(1)
        if cas not in seen:
            seen.add(cas)
            results.append(
                _make_result(
                    chemical=chemical,
                    claim_type=ClaimType.CAS_NUMBER,
                    value=cas,
                    unit="",
                    section_number=section_number,
                    original_text_span=match.group(0),
                    confidence=0.95,
                    **kwargs,
                )
            )

    return results


def extract_h_codes(
    text: str, section_number: int = 2, chemical: str = "", **kwargs
) -> list[ExtractionResult]:
    """Extract GHS H-codes (hazard statements) from SDS text."""
    results: list[ExtractionResult] = []
    seen: set[str] = set()

    for match in _regex_findall_safe(_H_CODE_RE, text):
        code = match.group(1).upper()
        if code not in seen:
            seen.add(code)
            results.append(
                _make_result(
                    chemical=chemical,
                    claim_type=ClaimType.H_CODE,
                    value=code,
                    unit="",
                    section_number=section_number,
                    original_text_span=match.group(0),
                    confidence=0.95,
                    **kwargs,
                )
            )

    return results


def extract_p_codes(
    text: str, section_number: int = 2, chemical: str = "", **kwargs
) -> list[ExtractionResult]:
    """Extract GHS P-codes (precautionary statements) from SDS text."""
    results: list[ExtractionResult] = []
    seen: set[str] = set()

    for match in _regex_findall_safe(_P_CODE_RE, text):
        code = match.group(1).upper()
        if code not in seen:
            seen.add(code)
            results.append(
                _make_result(
                    chemical=chemical,
                    claim_type=ClaimType.P_CODE,
                    value=code,
                    unit="",
                    section_number=section_number,
                    original_text_span=match.group(0),
                    confidence=0.95,
                    **kwargs,
                )
            )

    return results


def extract_exposure_limits(
    text: str, section_number: int = 8, chemical: str = "", **kwargs
) -> list[ExtractionResult]:
    """Extract occupational exposure limits (TWA, STEL, PEL, TLV) from SDS text."""
    results: list[ExtractionResult] = []

    for match in _regex_findall_safe(_EXPOSURE_RE, text):
        limit_type = match.group(1).upper()
        claim_type = (
            ClaimType.EXPOSURE_STEL if limit_type == "STEL" else ClaimType.EXPOSURE_TWA
        )
        results.append(
            _make_result(
                chemical=chemical,
                claim_type=claim_type,
                value=match.group(2),
                unit=match.group(3),
                section_number=section_number,
                original_text_span=match.group(0),
                confidence=0.88,
                **kwargs,
            )
        )

    return results


def extract_ppe(
    text: str, section_number: int = 8, chemical: str = "", **kwargs
) -> list[ExtractionResult]:
    """Extract PPE (Personal Protective Equipment) requirements from SDS text.

    Matches two source phrasings, both confirmed against real supplier SDS
    PDFs: sentence style ("wear nitrile gloves") and label:value style
    ("Hand protection\\nMaterial : Nitrile rubber"), the format that turned
    out to be dominant in a real batch of Sigma-Aldrich/GHS-EU SDS PDFs.
    """
    results: list[ExtractionResult] = []

    for match in _regex_findall_safe(_PPE_RE, text):
        ppe_item = match.group(1).strip().lower()
        results.append(
            _make_result(
                chemical=chemical,
                claim_type=ClaimType.PPE_REQUIREMENT,
                value=ppe_item,
                unit="",
                section_number=section_number,
                original_text_span=match.group(0),
                confidence=0.82,
                **kwargs,
            )
        )

    for match in _regex_findall_safe(_PPE_MATERIAL_RE, text):
        material = match.group(1).strip().lower()
        results.append(
            _make_result(
                chemical=chemical,
                claim_type=ClaimType.PPE_REQUIREMENT,
                value=material,
                unit="",
                section_number=section_number,
                original_text_span=match.group(0),
                confidence=0.85,
                **kwargs,
            )
        )

    return results


def extract_flash_point(
    text: str, section_number: int = 9, chemical: str = "", **kwargs
) -> list[ExtractionResult]:
    """Extract flash point from SDS text."""
    results: list[ExtractionResult] = []

    for match in _regex_findall_safe(_FLASH_POINT_RE, text):
        results.append(
            _make_result(
                chemical=chemical,
                claim_type=ClaimType.FLASH_POINT,
                value=match.group(1),
                unit=f"°{match.group(2).upper()}",
                section_number=section_number,
                original_text_span=match.group(0),
                confidence=0.90,
                **kwargs,
            )
        )

    return results


def extract_boiling_point(
    text: str, section_number: int = 9, chemical: str = "", **kwargs
) -> list[ExtractionResult]:
    """Extract boiling point from SDS text."""
    results: list[ExtractionResult] = []

    for match in _regex_findall_safe(_BOILING_POINT_RE, text):
        results.append(
            _make_result(
                chemical=chemical,
                claim_type=ClaimType.BOILING_POINT,
                value=match.group(1),
                unit=f"°{match.group(2).upper()}",
                section_number=section_number,
                original_text_span=match.group(0),
                confidence=0.90,
                **kwargs,
            )
        )

    return results


def extract_incompatibilities(
    text: str, section_number: int = 10, chemical: str = "", **kwargs
) -> list[ExtractionResult]:
    """Extract incompatible materials from SDS text."""
    results: list[ExtractionResult] = []

    for match in _regex_findall_safe(_INCOMPATIBILITY_RE, text):
        value = match.group(1).strip()
        if len(value) > 4:  # filter noise
            results.append(
                _make_result(
                    chemical=chemical,
                    claim_type=ClaimType.INCOMPATIBILITY,
                    value=value,
                    unit="",
                    section_number=section_number,
                    original_text_span=match.group(0),
                    confidence=0.80,
                    **kwargs,
                )
            )

    return results


# ---------------------------------------------------------------------------
# Master extractor — runs all patterns on a section
# ---------------------------------------------------------------------------

# Map: GHS section number → list of extraction functions to run on it.
_SECTION_EXTRACTORS: dict[int, list] = {
    2: [extract_h_codes, extract_p_codes],
    3: [extract_cas_numbers],
    7: [extract_storage_temp, extract_humidity],
    8: [extract_exposure_limits, extract_ppe],
    9: [extract_flash_point, extract_boiling_point],
    10: [extract_incompatibilities],
}


def extract_all_from_section(
    text: str,
    section_number: int,
    chemical: str = "",
    **kwargs,
) -> list[ExtractionResult]:
    """Run all relevant extractors on a single SDS section.

    Args:
        text: Raw section text.
        section_number: GHS section number (1–16).
        chemical: Chemical name for provenance.
        **kwargs: Passed through to each extractor (document_id, supplier, etc.).

    Returns:
        Combined list of ExtractionResult from all applicable extractors.
    """
    extractors = _SECTION_EXTRACTORS.get(section_number, [])
    results: list[ExtractionResult] = []

    for extractor in extractors:
        results.extend(
            extractor(text, section_number=section_number, chemical=chemical, **kwargs)
        )

    return results
