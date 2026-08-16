# ChemSentry — Team Roster

**Mapping: Team Member Names ↔ Roles (M1, M2, M3, M4)**

---

## Team Members

| Role | Member Name | GitHub Handle | Email | Responsibilities |
|---|---|---|---|---|
| **M1** | [Name] | @github-handle | email@domain.lk | Crawler, extraction, preprocessing, indexing |
| **M2** | [Name] | @github-handle | email@domain.lk | Retrieval cascade, ranking, evaluation suite |
| **M3** | [Name] | @github-handle | email@domain.lk | Reconciliation, safety states, classifier, Apriori, LLM |
| **M4** | Sahas Seneviratne | @github-handle | email@domain.lk | Agent C, IoT, security, gateway, UI, deployment |

---

## Quick Reference — What Each Member Owns

### M1 — Acquisition & Indexing
- **Directories:** `corpus/`, `extraction/`, `preprocessing/`, `indexing/`
- **Labs:** 02, 03, 07
- **Critical Week:** Week 4 (real data indexing)
- **Key Deliverable:** Inverted + positional index on live SDS corpus with versioning

### M2 — Retrieval & Evaluation
- **Directories:** `agents/agent_a_retrieval/`, `evaluation/`
- **Labs:** 04, 05, 06A
- **Critical Week:** Week 5 (first evaluation numbers)
- **Key Deliverable:** Full evaluation suite (P@5, R@10, MAP, latency, end-to-end accuracy)
- **Note:** Heaviest slice by design; this is where IR marks concentrate

### M3 — Analysis & Intelligence
- **Directories:** `agents/agent_b_analysis/`, `safety/`
- **Labs:** 06B, 08, 09
- **Critical Week:** Week 7 (deterministic safety logic)
- **Key Deliverable:** Deterministic SAFE/WARNING/UNKNOWN state machine (no LLM on this path)
- **Note:** Highest stakes — responsible for the Responsible AI claim

### M4 — IoT, Security & Delivery
- **Directories:** `agents/agent_c_environment/`, `firmware/`, `api/`, `ui/`, `marketing/`, `simulator/`
- **Labs:** 01, L12 + protocols
- **Critical Week:** Week 3–5 (hardware procurement, sensors publishing)
- **Key Deliverable:** ESP32 + DHT22 firmware, MQTT/TLS, FastAPI gateway, three UI modules, Docker deployment
- **Time-Sensitive:** Order hardware Week 3 (shipping delays block Week 5 milestone)

---

## Review Ring (Fixed)

Code review assignments follow a fixed ring, not ad hoc:

```
M1 → (reviews) → M2 → (reviews) → M3 → (reviews) → M4 → (reviews) → M1
```

**Everyone reviews the next slice in the ring.** This ensures each reviewer has real context on the adjacent slice, which makes cross-layer explainers (due end of Week 5) meaningful rather than theoretical.

---

## CODEOWNERS (Enforcement)

High-risk, shared surfaces require **2 reviewers**:

```
/agents/protocols/   → Requires approval from M2, M3, M4
/safety/             → Requires approval from M2, M3
/docs/architecture.md → Requires approval from all four
```

**Update `.github/CODEOWNERS`** with GitHub handles once all names are confirmed:

```
/agents/protocols/   @m2-handle @m3-handle @m4-handle
/safety/             @m2-handle @m3-handle
/docs/architecture.md @m1-handle @m2-handle @m3-handle @m4-handle
```

---

## Per-Member Week-by-Week Checklist

### M1 — Acquisition & Indexing

- **Week 3:** Environment setup, NLTK data download, test tokenizer on 5 sample SDS files
- **Week 4:** ✨ **CRITICAL** — Live indexing on full SDS corpus, demonstrate inverted index working
- **Week 5:** Provide indexed corpus to M2 for first evaluation
- **Week 6:** Refine tokenizer based on mid-eval feedback
- **Week 7:** Document extraction rationale (for viva prep)
- **Week 8–10:** Extend corpus, maintain versioning

### M2 — Retrieval & Evaluation

- **Week 3:** Set up evaluation benchmarks, define test queries, establish ground truth judgements
- **Week 4:** Build tolerant cascade (k-gram → Levenshtein → Soundex)
- **Week 5:** ✨ **CRITICAL** — First evaluation numbers (P@5, R@10, MAP, latency)
- **Week 6:** Mid-eval presentation, identify ranking gaps
- **Week 7:** Index elimination, source authority logic
- **Week 8–10:** Refine ranking, finalize evaluation report

### M3 — Analysis & Intelligence

- **Week 3:** Design safety state machine, define SAFE/WARNING/UNKNOWN criteria
- **Week 4:** Implement Jaccard conflict detection, version comparison logic
- **Week 5:** Receive first ranked results from M2, ready to reconcile
- **Week 6:** Mid-eval presentation, demonstrate deterministic state
- **Week 7:** ✨ **CRITICAL** — Deterministic safety layer live, no LLM on path
- **Week 8:** Add severity classifier, Apriori discovery
- **Week 9–10:** LLM orchestration (if evaluation on track), viva prep

### M4 — IoT, Security & Delivery

- **Week 3:** ✨ **CRITICAL** — Procure hardware (ESP32, DHT22, USB hub, breadboard), verify connectivity
- **Week 4:** Flash ESP32 firmware (PlatformIO), test DHT22 reads
- **Week 5:** ✨ **CRITICAL** — MQTT publishing to Mosquitto (TLS), integrate with Agent C
- **Week 6:** FastAPI gateway + JWT auth, demo live environment UI
- **Week 7:** Add reconciliation UI (view Agent A + Agent B outputs side by side)
- **Week 8:** Supervisor dashboard (sign-off queue), IoT loop closed end to end
- **Week 9–10:** Marketing site, CI/CD, deployment to staging

---

## Dependencies

| Week | Blocker | Who Needs It | Who Provides It |
|---|---|---|---|
| 4 | Indexed corpus | M2, M3 | **M1** |
| 5 | Ranked query results | M3 | **M2** |
| 5 | Sensors publishing MQTT | M3 (Agent C integration) | **M4** |
| 7 | Safety state machine | Entire system | **M3** |
| 8 | Complete Agent A + B pipeline | M4 (dashboard) | **M2 + M3** |

---

## Lab-to-Role Mapping

| Lab | Topic | Owner | Feeds |
|---|---|---|---|
| Lab 01 | Sensor simulator | M4 | M4 development |
| Lab 02 | Tokenization | M1 | preprocessing/ |
| Lab 03 | Inverted index | M1 | indexing/ |
| Lab 04 | k-gram & Levenshtein | M2 | agent_a_retrieval/ |
| Lab 05 | TF-IDF + cosine | M2 | agent_a_retrieval/ |
| Lab 06A | Index elimination | M2 | agent_a_retrieval/ |
| Lab 06B | Conflict detection | M3 | safety/reconciliation |
| Lab 07 | Regex extraction | M1 | extraction/ |
| Lab 08 | Decision tree classifier | M3 | agent_b_analysis/ |
| Lab 09 | Apriori rules | M3 | agent_b_analysis/ |
| L1–L5 | Lectures (foundations, IR theory) | All | Shared knowledge base |
| L6–L10 | Lectures (safety, RAI, compliance) | M3 leads, others attend | safety/ design |
| L12 | MQTT & protocols | M4 | api/, firmware/ |

---

## Status

- [ ] **M1 name:** [Pending]
- [ ] **M2 name:** [Pending]
- [ ] **M3 name:** [Pending]
- [x] **M4 name:** Sahas Seneviratne

**Next Step:** Fill in the three missing names, then update `.github/CODEOWNERS` with GitHub handles.

---

## Notes

- **M2 is the heaviest slice by design** — retrieval quality + full evaluation suite is where IR marks concentrate
- **M3 carries the highest stakes** — the safety decision must never touch the LLM; this is the Responsible AI claim
- **M4 is time-sensitive** — hardware procurement in Week 3 has shipping lead time; delays here block Week 5 milestone
- **All four share** Responsible AI Q&A prep and cross-layer explainers (due end of Week 5)
