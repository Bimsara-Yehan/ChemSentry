"""Prefix/suffix wildcard query resolution against the chemical-name vocabulary (Lab 04 / L3).

Real wildcard processing at IR scale narrows candidates via a k-gram or permuterm
index before checking anything directly, because scanning every document string is
too slow -- see kgram_index.py's own docstring, which already flags k-grams as "the
same trick" wildcard queries use. That index doesn't fit here without a redesign,
though: its grams are anchored only at the very start/end of the whole padded term,
but some benchmark wildcard queries must match a token *inside* a multi-word term --
evaluation/benchmarks/query_set.csv Q029 "per*" only resolves to "hydrogen peroxide"
via its second token, not the start of the whole string. Supporting that would mean
indexing every token separately. At this vocabulary's scale (a few dozen terms) a
direct per-token scan is simpler, provably correct against every benchmark row (see
evaluation/run_layer2_eval.py), and just as fast; it stops being the right call the
moment the vocabulary grows into the thousands, at which point a per-token k-gram (or
permuterm) index is the fix.

Supports exactly one wildcard per query, at the start or the end (`*chlorate`,
`hydro*`) -- the two forms in the benchmark set and ChemSentry_Final_Plan.md Part III
Section 5.3. Mid-term wildcards (`hy*ide`) aren't supported; nothing in the benchmark
or the plan calls for them.
"""


def resolve_wildcard(pattern: str, vocabulary: list[str]) -> list[str]:
    """Resolve a single prefix or suffix wildcard query to matching vocabulary terms.

    Matches if *any* whitespace-separated token of a vocabulary term satisfies the
    pattern -- e.g. "per*" matches "hydrogen peroxide" via its second token, and
    "sodium *" matches "sodium hydroxide" via its first. `pattern` must contain
    exactly one `*`, as the first or last non-whitespace character. Returns matches
    in vocabulary order; an empty list for a malformed pattern or no match.
    """
    normalized = pattern.strip().lower()
    if normalized.count("*") != 1:
        return []

    if normalized.startswith("*"):
        fixed = normalized[1:].strip()
        check = str.endswith
    elif normalized.endswith("*"):
        fixed = normalized[:-1].strip()
        check = str.startswith
    else:
        return []  # wildcard in the middle -- not supported, see module docstring

    if not fixed:
        return []

    return [
        term
        for term in vocabulary
        if any(check(token, fixed) for token in term.lower().split())
    ]
