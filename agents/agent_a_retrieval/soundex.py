"""Hand-built Soundex phonetic encoding -- fallback stage of the tolerant match
cascade (Lab 04 / L3).

k-gram + Levenshtein catches character-level typos ("tolune" for "toluene") but
misses phonetic misspellings where the letters differ but the sound doesn't
("ksylene" for "xylene"). Soundex groups letters by the consonant sound they
represent, so terms that sound alike collapse to the same code even when their edit
distance is large. Implemented by hand, per the project's classical-IR constraint --
no phonetics library in requirements.txt.

Simplification: multi-word chemical names are encoded as one run of letters (spaces
stripped) rather than per-token -- adequate for a fallback matching stage, not
intended as a full per-token phonetic index.
"""

_CODE_MAP = {
    **{c: "1" for c in "bfpv"},
    **{c: "2" for c in "cgjkqsxz"},
    **{c: "3" for c in "dt"},
    "l": "4",
    **{c: "5" for c in "mn"},
    "r": "6",
}


def soundex(term: str) -> str:
    """Return the 4-character Soundex code for `term`.

    Standard algorithm: keep the first letter, map remaining consonants to digit
    groups by sound, collapse adjacent letters that share a code (including
    across vowels, which are dropped but still break up runs), and pad/truncate to
    one letter plus three digits.
    """
    letters = [c for c in term.lower() if c.isalpha()]
    if not letters:
        return "0000"

    first_letter = letters[0]
    codes = [_CODE_MAP.get(c, "") for c in letters]

    deduped = [codes[0]]
    for code in codes[1:]:
        if code != deduped[-1]:
            deduped.append(code)

    digits = "".join(c for c in deduped[1:] if c)
    return (first_letter.upper() + digits + "000")[:4]
