"""Placeholder chemical-name vocabulary for the tolerant retrieval cascade (Lab 04).

Stands in for the term list M1's extraction pipeline (Lab 07) will eventually produce
from the real SDS corpus. Using a small hand-authored set lets the k-gram index,
Levenshtein matching, and Soundex fallback be built and tested now, without waiting on
indexing/extraction work that hasn't landed yet. Swap VOCABULARY for the real extracted
term list once corpus/, extraction/, and indexing/ are populated.

Spans suffix classes (-ate, -ide, -ol, -one) relevant to the suffix-wildcard retrieval
example in ChemSentry_Final_Plan.md Part III Section 5.3.
"""

VOCABULARY: list[str] = [
    "toluene",
    "acetone",
    "methanol",
    "ethanol",
    "isopropyl alcohol",
    "sodium hypochlorite",
    "hydrochloric acid",
    "sulfuric acid",
    "nitric acid",
    "sodium hydroxide",
    "ammonia",
    "formaldehyde",
    "hydrogen peroxide",
    "xylene",
    "ethyl acetate",
    "potassium permanganate",
    "sodium chlorate",
    "ferric chloride",
]
