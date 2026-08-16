# Evaluation Benchmarks

50 queries across five categories (exact, misspelled, wildcard, phrase, proximity), per
`ChemSentry_Final_Plan.md` Part VIII Layer 1. Owner: M2.

## `query_set.csv`

| Column | Meaning |
|---|---|
| `query_id` | Stable identifier (`Q001`-`Q050`), referenced by future eval scripts and relevance judgement files |
| `query_text` | The query itself. Wildcards use `*`; proximity queries use `term1 /N term2` meaning "within N words" |
| `category` | One of `exact`, `misspelled`, `wildcard`, `phrase`, `proximity` |
| `expected_chemicals` | For name-resolution categories (exact/misspelled/wildcard): the vocabulary term(s) the query should resolve to, semicolon-separated |
| `notes` | What the query is exercising and why |

## Status

The query set and category split are final. `expected_chemicals` for the
exact/misspelled/wildcard rows is filled in against the placeholder vocabulary in
`agents/agent_a_retrieval/vocabulary.py`, so those rows are usable for entity-resolution
evaluation (Layer 2) right now.

Phrase and proximity rows test document-content retrieval, not name resolution, so their
`expected_chemicals` is intentionally blank — there's no real SDS text yet to hand-assess
relevance against. Once M1's corpus/extraction/indexing work lands, add a
`relevant_doc_ids` column and fill in hand-assessed relevance judgements for all 50
queries per Layer 1 of the evaluation plan.
