# ChemSentry — Project Context for Claude Code

## What this is
Agentic AI system for IT3041 (Information Retrieval and Web Analytics). Domain: Chemical
Engineering. A retrieval-driven safety architecture: sensors detect a change, the system
retrieves the applicable rule from Safety Data Sheets, reconciles conflicting evidence, and
reaches a deterministic SAFE / WARNING / UNKNOWN state before any human is alerted.

**Central principle — do not violate this in any code you write:**
> No safety threshold is ever hardcoded. Every threshold is retrieved from a versioned
> source document at query time and cited back to the user.

## Architecture (in order)
```
Sensors (MQTT) → Agent C (env monitor, NO chemical knowledge)
→ Agent A (retrieval: k-gram/Levenshtein/Soundex → Boolean → index elimination → TF-IDF cosine)
→ Evidence Reconciler (source authority hierarchy, Jaccard conflict detection, versioning)
→ Deterministic Safety Layer (SAFE/WARNING/UNKNOWN — NO LLM on this path, ever)
→ Agent B (severity classifier, Apriori co-storage discovery, safety card)
→ LLM (summarise/translate ONLY — never decides safety)
→ Human sign-off (RBAC-gated, mandatory before any alert is final)
```

## Hard constraints — do not suggest violating these
- **No vector databases or embeddings** as the primary retrieval mechanism. This is a
  classical-IR project (inverted index, TF-IDF, k-grams) mapped deliberately to the module's
  labs. Embeddings may appear only as an optional comparison arm, never the core.
- **The LLM never touches the safety-decision path.** It only summarises, explains, and
  translates already-decided output. If a task looks like "let the LLM decide if this is
  dangerous," stop and flag it — that violates the design.
- **Apriori discovers co-storage patterns, not hazards.** Never label its output
  "dangerous pairing" directly — always route through a CAMEO/reactivity lookup first.
- **Wildcard/suffix matching is retrieval, not classification.** Don't infer hazard class
  from a chemical name suffix.
- **Three safety states only: SAFE / WARNING / UNKNOWN.** Never force a SAFE/WARNING verdict
  when evidence is missing or conflicting — return UNKNOWN instead.

## Tech stack
- Python 3.11, FastAPI + Pydantic, MCP Python SDK for agent-to-agent calls
- Retrieval: hand-built inverted/positional index (Lab 03), hand-built k-gram + `nltk`
  edit_distance (Lab 04), `sklearn.TfidfVectorizer` + cosine (Lab 05), hand-built index
  elimination (Lab 06A)
- Extraction: `re` (Lab 07) — primary extraction path, LLM only for residue
- Classification: `sklearn.DecisionTreeClassifier`, `class_weight='balanced'` (Lab 08)
- Association rules: `mlxtend.apriori` + `association_rules` (Lab 09)
- IoT: ESP32 + DHT22, MQTT/TLS (Mosquitto), `paho-mqtt`
- DB: PostgreSQL (or SQLite for local dev) via SQLAlchemy
- Frontend: React + Vite + Tailwind + Recharts
- Full stack detail: see `/docs/architecture.md` and `setup.md`

## Repository layout
One top-level directory per team member's slice — see `setup.md` Section 1 for the full
tree. Don't scatter one person's work across another's directory; it breaks individual
contribution tracking for the viva.

| Member | Owns |
|---|---|
| M1 | `corpus/`, `extraction/`, `preprocessing/`, `indexing/` |
| M2 | `agents/agent_a_retrieval/`, `evaluation/` |
| M3 | `agents/agent_b_analysis/`, `safety/` |
| M4 | `agents/agent_c_environment/`, `firmware/`, `api/`, `ui/`, `marketing/` |

## Coding standards
- Format with Black, lint with Ruff, before every commit
- Every function gets a docstring explaining what problem it solves and why this technique
  over a simpler one (see `docs/adr/` for precedent) — this is direct viva prep material
- Tests go in `tests/`, one directory per component; `pytest` must pass before merge
- Comment professionally: explain *why*, not just *what* — especially anywhere the code
  diverges from the lab reference implementation (documented divergences: chemical-identifier
  protection in preprocessing, domain tokenizer instead of `.split()`, selective stemming)

## Evaluation is not optional
The IR evaluation suite (`evaluation/`) is a Week 5 deliverable, not a Week 9 one. If asked
to build a retrieval feature without a corresponding benchmark query, flag it.

## Full plans
`setup.md` — environment setup, installs, hardware, Git workflow
`docs/architecture.md` — full system design, agent responsibilities, evaluation plan
