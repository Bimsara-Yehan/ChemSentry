# ChemSentry — Team Plan

The single reference for **who does what, how decisions get made, and how the ten
weeks are paced.** For system architecture and technical rationale, see
`ChemSentry_Final_Plan.md`. For Git mechanics, see `Branching_and_Delegation_Strategy.md`.

---

## 1. The Team at a Glance

| | Owns | Final say on | Reviews | Labs / Lectures |
|---|---|---|---|---|
| **M1** | Crawler, extraction, preprocessing, indexing | Corpus format, tokenizer behaviour | M2 | Lab 02, 03, 07 · L1, L2, L11 |
| **M2** | Retrieval cascade, ranking, evaluation suite | What counts as a passing benchmark | M3 | Lab 04, 05, 06A · L3, L4, L5 |
| **M3** | Reconciliation, safety states, classifier, Apriori, LLM layer | Safety-state logic, RAI boundary | M4 | Lab 06B, 08, 09 · L6–L10 |
| **M4** | Agent C, IoT, security, gateway, UI, deployment | Infra, deployment, API contracts | M1 | Lab 01 · L12 + protocols |

**Review ring:** M1 → M2 → M3 → M4 → M1. Fixed, not ad hoc — everyone has real context
on the slice next to theirs, which is what makes the Week 5 cross-layer explainers
useful rather than theoretical.

**The important role, by design:** M2. This is an IR module — the evaluation suite is
the only thing that proves the project is an IR contribution rather than a chemical
safety demo. It's also the heaviest slice. If it slips, the whole project's core
claim slips with it. **M3 carries the highest stakes** in a different sense: the
deterministic safety gate must never have an LLM on its path, which is why changes
there require two reviewers, not one (see §5).

---

## 2. What Each Member Builds

### Member 1 — Acquisition & Indexing
- SDS crawler, respecting `robots.txt` and politeness delays
- Regex extraction pipeline: CAS numbers, GHS codes, temperature/exposure limits
- Preprocessing: tokenizer, stop words, stemming — with chemical identifiers
  protected from all three
- Inverted + positional index built on the real corpus
- Document versioning metadata

**Critical week:** Week 4 — plain lab-derived indexing working on real data, before
anyone builds on top of it.

### Member 2 — Retrieval & Evaluation
- Tolerant retrieval cascade: k-gram → Levenshtein → Soundex
- TF-IDF cosine ranking
- Index elimination
- Source authority hierarchy logic
- **The full evaluation suite** — P@5, R@10, MAP, latency, entity-resolution
  accuracy, end-to-end safety-state accuracy

**Critical week:** Week 5 — first real evaluation numbers, before mid-eval.

### Member 3 — Analysis & Intelligence
- Evidence reconciler: version comparison, Jaccard conflict detection
- Deterministic SAFE / WARNING / UNKNOWN state machine — no LLM on this path
- Severity classifier (class-weighted, confusion matrix reported)
- Apriori co-storage discovery, framed as discovery not hazard classification
- Rule-based chat fast path
- LLM layer: summarisation, translation, open-query orchestration only

**Critical constraint:** the safety decision is never made by the LLM. This is the
project's central Responsible AI claim — see `ChemSentry_Final_Plan.md` Part VII.

### Member 4 — IoT, Security & Delivery
- Agent C — zone state and excursion detection, holds no chemical knowledge
- ESP32 + DHT22 firmware, MQTT/TLS
- FastAPI gateway, JWT auth, RBAC
- Three UI modules: Live Environment, Reconciliation, Supervisor Dashboard
- Docker Compose deployment, CI
- Marketing site + GA4

**Time-sensitive task:** order hardware in Week 3 — shipping delays threaten the
Week 5 "sensors publishing" milestone.

---

## 3. Shared by All Four

- **Responsible AI and commercialisation** — the viva panel directs these questions
  at whoever it chooses, so everyone needs a working answer, not just their own layer
- **Cross-layer explainers** — a half-page write-up of your own slice for the other
  three, due end of Week 5
- **`safety/` and `agents/protocols/`** — shared, high-risk surfaces; any change here
  needs sign-off from the affected owners via `CODEOWNERS`, not just the usual
  reviewer

---

## 4. Decision Rights & Escalation

Each member has final say inside their own domain (§1). For anything cross-cutting —
an API contract change, a database schema change, an MCP tool signature change:

1. Open an issue *before* opening a PR, tagged `cross-cutting`
2. State what changes and why
3. Affected owners get 24 hours to object or approve, async
4. Unresolved after 24 hours → raised at the next weekly sync, not left blocking
   silently

---

## 5. Review Rules

- **1 approving review** to merge, for ordinary PRs — via the rotation in §1
- **2 approving reviews** for anything touching `safety/` or `agents/protocols/`,
  enforced via `CODEOWNERS`
- **48-hour review SLA** — if you can't review in time, say so on the PR rather than
  letting it go quiet
- Merge via merge commit, not squash — keeps individual authorship visible in
  history (see `Branching_and_Delegation_Strategy.md` §I.4 for why this matters for
  the viva)

---

## 6. Weekly Cadence

- **One sync per week**, ~20 minutes, right after your lab session
- **Async standup** in your team chat: what you finished, what you're starting,
  what's blocking you
- Keep the GitHub Issues board current between syncs so the weekly meeting is status
  confirmation, not status discovery

---

## 7. Definition of Done

A task is done when:

- [ ] Code is committed to a feature branch, pushed
- [ ] At least one test exists for it
- [ ] It's referenced to the relevant lab/lecture in a docstring, per `CLAUDE.md`
- [ ] PR opened, reviewed per §5, merged
- [ ] If it changes retrieval behaviour — evaluation suite re-run, results updated

---

## 8. Timeline

| Week | Milestone | Primary owner |
|---|---|---|
| 3 | Repo, standards, domain registered. Crawler skeleton. Benchmark query set drafted. | All |
| 4 | Regex extraction, preprocessing, inverted + positional index on real data. | M1 |
| 5 | Tolerant cascade, TF-IDF ranking. **First evaluation numbers.** Sensors publishing. | M2, M4 |
| **6** | **MID EVALUATION** — architecture, agent flow, live demo, first metrics, RAI check, pitch | All |
| 7 | Index elimination, Jaccard conflict detection, deterministic safety layer. | M2, M3 |
| 8 | Severity classifier, Apriori discovery, supervisor dashboard, IoT loop closed. | M3, M4 |
| 9 | Full evaluation run, fairness testing, marketing site + GA4, report drafting, video. | All |
| **10** | **FINAL SUBMISSION** — video, report, GitHub repo | All |
| **11** | **VIVA** | All |

**Freeze windows:** two days before Week 6 and Week 10 — fixes only, no new feature
merges.

---

## 9. Related Documents

| Document | Covers |
|---|---|
| `ChemSentry_Final_Plan.md` | Full system architecture, syllabus mapping, evaluation plan, Responsible AI |
| `setup.md` | Environment setup, installs, hardware procurement |
| `TECH_STACK.md` | Technology choices and what to download, standalone reference |
| `Branching_and_Delegation_Strategy.md` | Git branching model, commit conventions, CODEOWNERS detail |
| `CLAUDE.md` | Project context auto-loaded by Claude Code every session |
