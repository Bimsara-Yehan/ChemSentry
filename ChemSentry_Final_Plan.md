# ChemSentry — Final Project Plan (v4)
### IT3041 — Agentic AI System Development

**Domain:** Chemical Engineering
**Team size:** 4
**Status:** consolidated plan, incorporating two rounds of external review

---

## Part I — The Idea

### 1. Central Research Question

Everything in this project answers one question. If a subsystem doesn't serve it, we cut the subsystem.

> **Can classical information retrieval and evidence reconciliation dynamically connect real-world environmental conditions with authoritative chemical safety documentation — without hardcoded chemical knowledge and without LLM-generated safety decisions?**

### 2. The Architecture in Seven Words

```
IR         = the brain
IoT        = the eyes
Agents     = the workers
Documents  = the knowledge source
Rules      = the safety barrier
LLM        = the communication layer
Human      = the final authority
```

Memorise this. It is the answer to "so what is your project?" and every one of us should give the same answer.

### 3. Positioning

> **An evidence-grounded, retrieval-driven safety decision-support architecture that dynamically connects physical conditions with versioned chemical safety documentation.**

Not a monitoring dashboard. Not a chatbot. Not a SaaS pitch. A retrieval architecture that happens to have sensors attached.

---

## Part II — The Problem

Picture a mid-size dyeing or rubber processing plant. Eighty-odd chemicals in the store room, each with a supplier-issued Safety Data Sheet sitting unread in a binder.

**Problem 1 — The sheets contradict each other.**
Two suppliers, two sheets, different storage ceilings and hazard classifications. Nobody reconciles them because reconciling eighty substances by hand isn't realistic.

**Problem 2 — Nothing connects the document to the room.**
The sheet says "store below 25 °C." That's a PDF. The store room is a physical place. Breaches surface during audits, or during incidents.

**Problem 3 — The people at risk can't read the documents.**
Safety Data Sheets are published in English. The operators handling the drums often read Sinhala or Tamil.

**The principle that follows:**

> **No safety threshold is hardcoded. Every threshold is retrieved from a versioned source document at query time, and cited back to the user.**

A normal monitoring system says `if (temp > 25) alarm()`. Ours knows no safe temperatures. It searches the safety documentation for whatever chemicals are in that room today, extracts the declared limit, and compares. That is why this is an Information Retrieval project.

---

## Part III — Why This Scores

### 4. Full Syllabus Coverage

Most groups will build an LLM chatbot over a vector database. That demonstrates almost nothing from our syllabus — our module teaches *classical* IR. Embeddings and vector databases appear in none of our twelve lectures or nine labs.

| We need to… | Which requires… | Taught in |
|---|---|---|
| Find storage rules for a chemical | Inverted + positional index | Lab 03, L1–2 |
| Handle "tolune" typed for "toluene" | k-grams, Levenshtein, Soundex | Lab 04, L3 |
| Retrieve all name-pattern matches at once | Wildcard / k-gram queries | Lab 04, L3 |
| Rank which passage answers the question | TF-IDF + cosine | Lab 05, L4 |
| Stay fast enough for a live alert | Index elimination | Lab 06A, L5 |
| Pull "≤25 °C" out of messy PDF text | Regex | Lab 07 |
| Rate incident severity | TF-IDF + Decision Tree | Lab 08, L6 |
| Discover co-storage patterns | Apriori association rules | Lab 09, L7–8 |
| Find where two suppliers disagree | Jaccard similarity | Lab 04 + Lab 06 |
| Collect the documents | Crawling, robots.txt, politeness | L11 |
| Explain and translate the alert | LLM | L10 |
| Evidence the commercial case | SEO + Google Analytics | L12 |

Every lecture, every lab, nothing decorative.

### 5. The Three Differentiators

**5.1 — We use duplicate detection backwards.**
Lecture 11 and Lab 04 teach Jaccard similarity so a crawler can *discard* near-duplicates. Two supplier sheets for the same chemical are textbook near-duplicates at 85–95% overlap. We compute the same score and **keep the difference** — the shingles present in only one sheet are exactly where the suppliers disagree. Same algorithm, opposite purpose.

**5.2 — Association-rule mining discovers co-storage patterns.**
Lab 09 mines *users who watched A also watched B*. We treat each storage zone's inventory as a transaction:

```
{sodium hypochlorite} → {hydrochloric acid}
support 0.34 · confidence 0.71 · lift 2.1
```

**Important framing:** Apriori is a **discovery** mechanism, not a hazard classifier. Association does not establish chemical incompatibility. The pipeline is:

```
Apriori → common co-storage pair → CAMEO compatibility lookup
       → known incompatibility? → potential safety issue → human review
```

We call this **co-storage anomaly discovery**, never "dangerous pairing detection."

**5.3 — Chemical nomenclature makes wildcard queries efficient.**
Names are suffix-structured (`-ate`, `-ide`, `-ol`, `-one`), so `*chlorate` retrieves a meaningful candidate set in one query.

**Important framing:** the wildcard is a **retrieval mechanism**, not a classifier. Hazard class comes from authoritative metadata, never inferred from the suffix. Correct wording:

> Wildcard matching efficiently retrieves chemicals whose names contain a target pattern; hazard classification is obtained from authoritative chemical metadata rather than inferred from the name.

---

## Part IV — The Safety Model

This section is the biggest change from earlier drafts and the strongest part of the project.

### 6. Three Safety States

The system is never forced to produce a verdict.

| State | Meaning |
|---|---|
| **SAFE** | Sufficient evidence exists and the observed condition satisfies the documented requirement |
| **WARNING** | Sufficient evidence exists and the observed condition violates or approaches a documented requirement |
| **UNKNOWN / REVIEW REQUIRED** | The applicable requirement cannot be confidently determined — evidence missing, conflicting, outdated, or ambiguous |

> **The system never converts uncertainty into a confident safety verdict.**

Being able to say that in the viva, and then *demonstrate* an UNKNOWN state on a real query, is worth more than any accuracy number we can report.

### 7. Source Authority Hierarchy

Our six corpora are not equally authoritative for every question. The retrieval layer consults this table before ranking.

| Question type | Preferred source | Fallback |
|---|---|---|
| Storage conditions | Supplier SDS (Section 7) | NIOSH |
| PPE | Supplier SDS (Section 8) | NIOSH |
| Exposure limits | NIOSH / regulatory source | Supplier SDS |
| Chemical identity & synonyms | PubChem | Supplier SDS |
| Reactivity & incompatibility | CAMEO | Supplier SDS (Section 10) |
| Historical incidents | US Chemical Safety Board | — |

### 8. Conflict Resolution

Detect, don't silently resolve.

1. Detect the conflict (Jaccard difference between sheets)
2. Identify source, supplier, and document version
3. Apply a conservative **temporary control threshold** for alerting
4. Explicitly mark the conflict for human review
5. **Do not present the conservative value as the definitive scientific requirement**

Report wording:

> When authoritative sources conflict, the system applies a conservative temporary control threshold for alerting while explicitly flagging the conflict for human review.

Different suppliers may legitimately differ by formulation, concentration, grade, regulatory jurisdiction, or document age. We are not qualified to adjudicate that — and saying so is the correct answer, not a weakness.

### 9. Provenance Model

Every safety-related claim carries full provenance:

```
chemical · claim · document_id · supplier · sds_revision
revision_date · section_number · page_number · original_text_span
extraction_method · confidence · source_authority
```

Rendered alert:

```
ALERT

Chemical:              Toluene
Zone:                  B
Observed temperature:  31 °C

Retrieved storage guidance:  ≤ 25 °C

Source:      ABC Chemicals SDS
Revision:    2026-02
Section:     7 (Handling and Storage)
Page:        5
Extraction:  regex, confidence 0.94
Authority:   supplier SDS (preferred for storage conditions)

Reason:      Observed temperature exceeds retrieved guidance.
Status:      HUMAN REVIEW REQUIRED
```

### 10. Document Versioning

Store per document: `chemical · supplier · sds_version · revision_date · retrieval_date`.

Retrieval prefers current versions. Where versions disagree, that is itself a conflict requiring review.

This creates a genuine research sub-question worth stating in the report:

> How should an evidence-grounded safety system reason when multiple versions of authoritative documents exist?

**Scope note:** metadata and preference logic only. We are not building version diffing.

---

## Part V — System Architecture

### 11. Conceptual Flow

```
              ┌──────────────────────────┐
              │   Physical Environment   │
              └────────────┬─────────────┘
                           ▼
              ┌──────────────────────────┐
              │  AGENT C — Environmental │
              │  "Something changed"     │
              │  (holds no chemical      │
              │   knowledge whatsoever)  │
              └────────────┬─────────────┘
                           ▼
              ┌──────────────────────────┐
              │   Context Construction   │
              │  chemical + zone +       │
              │  condition + timestamp   │
              └────────────┬─────────────┘
                           ▼
              ┌──────────────────────────┐
              │  AGENT A — Retrieval     │
              │  name resolution (L04)   │
              │  Boolean retrieval (L03) │
              │  positional search (L03) │
              │  TF-IDF cosine     (L05) │
              │  index elimination (L06) │
              │  source authority        │
              └────────────┬─────────────┘
                           ▼
              ┌──────────────────────────┐
              │  Evidence Reconciler     │
              │  version comparison      │
              │  Jaccard conflict (L04)  │
              │  evidence confidence     │
              └────────────┬─────────────┘
                           ▼
              ┌──────────────────────────┐
              │  DETERMINISTIC SAFETY    │
              │  REASONING LAYER         │
              │  → SAFE / WARNING /      │
              │    UNKNOWN               │
              │  (no LLM on this path)   │
              └────────────┬─────────────┘
                           ▼
           ┌───────────────┴───────────────┐
           ▼                               ▼
    Safety state                    Explanation
           ▼                               ▼
    Human reviewer            LLM: summarise / translate
           └───────────────┬───────────────┘
                           ▼
                    Safety Alert
```

### 12. The Three Agents

| Agent | Role | Hard constraint |
|---|---|---|
| **A — Retrieval** | Given a chemical and an information need, returns ranked cited evidence | Never issues a safety verdict. Returns evidence with provenance only |
| **B — Analysis** | Reconciles evidence, detects conflicts, classifies severity, mines co-storage patterns, generates the safety card | Deterministic rules produce the safety state; the LLM only phrases it |
| **C — Environmental Monitor** | Subscribes to telemetry, tracks zone state, detects excursions | Holds no chemical knowledge. Knows Zone B is at 31 °C; does not know whether that matters. **Must ask.** |

That last constraint is what makes this a genuine multi-agent system rather than one program with three modules. Expect it as a viva question.

### 13. Where the LLM Sits — Two Paths

Earlier reviews pulled in opposite directions here. The resolution is a deliberate split, and stating it explicitly is a strength.

**Safety path — fully deterministic. The LLM never decides.**

```
sensor → retrieval → structured evidence → deterministic rules
       → safety state → LLM (explanation and translation only)
```

Never `documents → LLM → safety decision`.

**Open-ended query path — LLM-orchestrated.**
When a safety officer asks *"why did Zone B alert last Tuesday?"*, an LLM decides which tools to call via MCP: the inverted index, the incident corpus, the co-storage rules, or several in sequence. It selects tools; the tools are classical IR. It reads results; it does not invent rules.

**Why the split:** the brief requires agentic behaviour, but nondeterminism on a safety-critical path is a liability. We get demonstrable tool selection *and* a provable safety path. Defending this split is a better viva answer than "we made everything agentic."

### 14. Agent Communication Protocols

| Protocol | Between | Why |
|---|---|---|
| **MQTT (TLS)** | Sensors → Agent C | Lightweight pub-sub for constrained devices; QoS where delivery matters |
| **MCP** | Agent ↔ Agent | Typed tool schemas; native fit for LLM tool selection; self-describing |
| **HTTPS / REST** | Gateway → clients | Universal, stateless, well-understood auth |

MCP stays. The brief names it explicitly under required communication protocols, and the viva examines "understanding of communication protocols" as a scored criterion. Justifying *why each protocol suits its specific link* is the point.

---

## Part VI — Implementation

### 15. Pipeline

```
ACQUISITION      crawler · robots.txt · politeness · frontier        (L11)
      ↓
EXTRACTION       regex: 16 GHS sections · CAS · H-codes · limits     (Lab 07)
      ↓
PREPROCESSING    lowercase · punctuation · tokenize · stem           (Lab 02)
                 …with chemical identifiers protected
      ↓
INDEXING         inverted + positional index · k-gram index    (Lab 03, 04)
      ↓
RETRIEVAL        tolerant cascade → Boolean → elimination → TF-IDF cosine
      ↓
RECONCILIATION   source authority · version preference · Jaccard conflict
      ↓
SAFETY REASONING deterministic rules → SAFE / WARNING / UNKNOWN
      ↓
COMMUNICATION    LLM summary · Sinhala/Tamil card · human sign-off
```

### 16. IoT Layer — Simplified

**Core physical pipeline (must work):**

```
ESP32 + DHT22 → MQTT/TLS → Agent C → zone inventory
              → retrieval → evidence → safety state
```

**Inventory is database-backed and simulated** (`Zone B contains: toluene, acetone, methanol`). Container tracking is not our research contribution.

| Item | Status | ~LKR |
|---|---|---|
| ESP32 DevKit ×2 | Core | 5,000 |
| DHT22 ×2 | Core | 1,200 |
| Wiring, breadboard, PSU | Core | 2,000 |
| MQ-135 VOC | Optional extension | 900 |
| RC522 RFID + tags | Optional extension | 2,500 |

**Two honesty points for the report:**

Cheap MQ gas sensors are **not substance-selective**. If we include one, we frame it as an anomaly trigger that initiates retrieval, never a chemical identifier.

We build a **simulator** publishing to identical MQTT topics. Demo normal operation live, hazard scenarios simulated, and label clearly which is which.

### 17. Security

| Layer | Control |
|---|---|
| Device | Per-device TLS certificates for MQTT; unregistered device IDs rejected |
| Telemetry | Schema validation, range checks, rate limiting before any value reaches a prompt |
| Extraction | **Regex timeouts and bounded quantifiers to prevent ReDoS** — our regex layer is the primary extraction path and catastrophic backtracking would hang the pipeline |
| Crawler | Path-traversal protection on file writes; domain allowlist |
| LLM boundary | Prompt-injection sanitisation on all free-text and telemetry-derived input |
| Application | JWT auth; RBAC across Operator / Safety Officer / Administrator — this is what enforces human-in-the-loop |
| Data | Encryption at rest for inventory data; append-only audit log of every alert and sign-off |

**Viva point worth rehearsing:** a spoofed sensor reading is both an industrial IoT attack and a prompt-injection vector. Telemetry validation serves two distinct security purposes.

### 18. User Interface

Three surfaces, separate navigation:

**Live Environment Module** — real-time zone conditions and inventory.

**Document Reconciliation Module** — query the safety documentation, view conflicts between suppliers.

**Supervisor Dashboard** — pending sign-offs, active alerts, plant compliance status, historical alert log. This is what makes human-in-the-loop *visible* rather than asserted; it demos in ninety seconds.

**One deliberate exception to the separation:** the alert detail view shows sensor reading and cited document **side by side**. Temperature reads 31 °C, and immediately beside it the line from Section 7 saying 25 °C, with supplier and revision. That juxtaposition is the entire thesis in one screenshot — it must not be split across two screens.

---

## Part VII — Responsible AI

### 19. Designed In, Not Bolted On

**The boundary — our strongest claim.** ChemSentry retrieves and reconciles published safety documentation. It does **not** advise on chemical procedures, propose reactions, recommend process conditions, or suggest formulations. Enforced in system prompts, tool schemas, and the UI. When asked why: an LLM giving operational chemical guidance is an unacceptable safety risk regardless of apparent accuracy.

**The LLM never decides safety.** Deterministic rules produce the state; the LLM phrases it. See §13.

**Uncertainty is preserved, not resolved.** The UNKNOWN state exists precisely so the system can decline to answer. See §6.

**Conflicts are surfaced, not hidden.** Conservative alerting threshold, flagged for review, never presented as definitive. See §8.

**Full provenance on every claim.** No verdict without a traceable source. See §9.

**Human is final authority.** No alert auto-closes. No safety card reaches the floor without Safety Officer sign-off — enforced by RBAC, visible in the supervisor dashboard.

**Safety-critical questions bypass the LLM entirely.** Lab 06B rule-based keyword matching handles known-shape questions ("PPE for toluene") deterministically from extracted values.

**Fairness — testable, not asserted.** Two tests: does retrieval degrade for chemicals with fewer indexed sheets? And is Sinhala/Tamil output equal in completeness to English, or does the non-English reader receive a degraded safety message? The second is a fairness question with a safety consequence.

---

## Part VIII — Evaluation

### 20. Five Evaluation Layers

This is where IR marks concentrate. First numbers by **Week 5**, before mid-evaluation.

**Layer 1 — Retrieval quality** (50 hand-assessed queries: exact, misspelled, wildcard, phrase, proximity)

| Configuration | P@5 | R@10 | MAP | Latency |
|---|---|---|---|---|
| Boolean only (Lab 03) | | | | |
| + TF-IDF cosine (Lab 05) | | | | |
| + index elimination (Lab 06A) | | | | |
| + tolerant matching (Lab 04) | | | | |

The latency column is the point — Lab 06 exists to show elimination trades a little relevance for a lot of speed.

**Layer 2 — Entity resolution** (against PubChem ground truth, with injected typos)

| Input | Exact | k-gram + Levenshtein | Soundex | Unresolved |
|---|---|---|---|---|
| Clean | | | | |
| 1 typo | | | | |
| 2 typos | | | | |
| Phonetic | | | | |

**Layer 3 — Information extraction** — did regex pull the right value? Precision, recall, F1, and normalised-value exact-match on temperature limits, humidity limits, PPE, exposure limits.

**Layer 4 — Conflict detection** — true conflicts detected, false conflicts, missed conflicts.

**Layer 5 — End-to-end state accuracy** — the most impressive table we will produce:

| Ground truth | System SAFE | System WARNING | System UNKNOWN |
|---|---|---|---|
| SAFE | | | |
| WARNING | | | |
| UNKNOWN | | | |

The UNKNOWN row proves the system handles uncertainty rather than manufacturing verdicts. Lead the report's results section with this.

**Also:** severity classifier `classification_report`, confusion matrix, and balanced-vs-unbalanced minority-class F1 — critical hazards are rare, so accuracy alone misleads.

---

## Part IX — Commercialisation

### 21. Positioning

Supporting layer, not the headline. The report must not read as a startup pitch — the central narrative stays "intelligent retrieval-driven safety architecture." But the work stays at **full weight**: commercialisation appears in the mid-evaluation, the report, *and* the viva as a named scored component.

**Target market:** Sri Lankan process-industry SMEs, 20–200 employees — textile dyeing and finishing, rubber, tea, food manufacturing, agrochemical blending.

**The gap:** enterprise EHS platforms cost more than these firms will approve. Free tools are static PDF repositories. Nobody serves the middle.

| Tier | Price/month | Includes |
|---|---|---|
| Free | — | 25 substances, reconciliation only, no IoT, 1 user |
| Standard | USD 49 | 150 substances, 2 zones, 5 users, Sinhala/Tamil cards |
| Professional | USD 149 | Unlimited substances, 10 zones, incident search, audit export |
| Self-hosted | USD 1,800/yr | On-premises, local model, no external data egress |

**The insight to lead with:** many local manufacturers operate under export-client contracts prohibiting transmission of operational data to third-party clouds. The self-hosted tier is the difference between a closed deal and a lost one.

**Evidence over assertion:** the marketing site carries real SEO and GA4 funnel tracking (L12), so we report measured visitor-to-trial conversion rather than guessed numbers.

**Present this at the mid-evaluation.** It is one of five listed components of a 20-mark deliverable — allocate slide time, not a closing sentence.

---

## Part X — Execution

### 22. Team Allocation

| | Owns | Labs | Lectures |
|---|---|---|---|
| **M1** | Crawler · regex extraction · preprocessing · inverted + positional index · document versioning | 02, 03, 07 | L1, L2, L11 |
| **M2** | Tolerant retrieval cascade · TF-IDF ranking · index elimination · source authority logic · **full evaluation suite** | 04, 05, 06A | L3, L4, L5 |
| **M3** | Evidence reconciler · safety state logic · severity classifier · Apriori discovery · rule-based chat · LLM layer | 06B, 08, 09 | L6–L10 |
| **M4** | Agent C · IoT · MQTT · security · gateway · three UI modules · deployment · marketing site + GA4 | 01 | L12 + protocols |

**Shared by all four:** Responsible AI reasoning and commercialisation. The panel directs these at whoever it chooses.

**M2 carries the heaviest marked load.** Retrieval quality plus evaluation is where IR marks concentrate — assign accordingly.

**Cross-training:** each of us reviews PRs on one adjacent layer and writes a half-page internal explainer of our own layer for the other three, by end of Week 5.

### 23. Timeline

| Week | Lands | Owner |
|---|---|---|
| **3** | Repo, standards, domain registered. Crawler skeleton. Benchmark query set drafted. Safety states and provenance model agreed. | All |
| **4** | Regex extraction. Preprocessing. Inverted + positional index on real chemistry data. Versioning metadata. | M1 |
| **5** | Tolerant cascade. TF-IDF ranking. Source authority table. **First evaluation numbers.** Sensors publishing. | M2, M4 |
| **6** | **MID EVALUATION** — architecture, agent flow, live retrieval demo, first metrics, RAI check, **commercialisation pitch** | All |
| **7** | Index elimination. Jaccard conflict detection. Deterministic safety-state layer. Rule-based chat. | M2, M3 |
| **8** | Severity classifier. Apriori discovery + CAMEO lookup. Supervisor dashboard. IoT loop closed end to end. *LLM orchestrator if evaluation is on track.* | M3, M4 |
| **9** | Full five-layer evaluation. Fairness testing. Marketing site + GA4. Report. Gen-AI video. | All |
| **10** | **FINAL SUBMISSION** — video, report, GitHub | All |
| **11** | **VIVA** | All |

Video must use Synthesia, HeyGen, Pika or similar. A screen recording doesn't meet the brief.

### 24. Repository Structure

5 marks, with a graded README.

```
chemsentry/
├── README.md                  setup · usage · architecture · contributors
├── docs/
│   ├── architecture.md
│   ├── responsible-ai.md
│   ├── evaluation-results.md
│   └── adr/                   architecture decision records
├── corpus/
│   ├── crawler/               L11 — frontier, robots.txt, politeness
│   └── raw/                   .gitignored, fetch script provided
├── extraction/                Lab 07 — regex, section splitting
├── preprocessing/             Lab 02 — tokenizer, stemming
├── indexing/                  Labs 03, 04 — inverted, positional, k-gram
├── agents/
│   ├── agent_a_retrieval/
│   ├── agent_b_analysis/
│   ├── agent_c_environment/
│   └── protocols/             MCP tool schemas
├── safety/                    deterministic rules, state machine, provenance
├── firmware/                  ESP32 sketches
├── simulator/                 MQTT telemetry simulator
├── api/                       FastAPI gateway, auth, RBAC
├── ui/
│   ├── live-environment/
│   ├── reconciliation/
│   └── supervisor/
├── evaluation/
│   ├── benchmarks/            query sets + relevance judgements
│   └── results/               generated tables
└── marketing/                 site + GA4 config (L12)
```

One top-level directory per member's slice where possible — it makes individual contribution visible in the commit history, which the viva checks.

### 25. Deliverables

**Week 6 — Mid Evaluation (20)**
- [ ] System architecture
- [ ] Agent roles and communication flow
- [ ] Live retrieval demo
- [ ] First evaluation numbers
- [ ] Responsible AI compliance check
- [ ] Commercialisation concept pitch

**Week 10 — Final (60)**
- [ ] Gen-AI video, 3–5 min
- [ ] Report: design, methodology, RAI, commercialisation with pricing, evaluation results
- [ ] GitHub repo with detailed README

**Week 11 — Viva (20)**
- [ ] Each member fluent in their own labs and lectures
- [ ] All four able to answer on RAI and pricing
- [ ] Protocol choices justified per link
- [ ] Evaluation numbers known, not read

---

## Part XI — Risks and Discipline

### 26. Risk Register

| Risk | Mitigation |
|---|---|
| PDF parsing unreliable across suppliers | Start Week 3. Curate a well-parsed subset rather than chasing universal coverage |
| Retrieval ends up as one similarity call with no metrics | Evaluation is a Week 6 deliverable, not Week 9 |
| We reach for embeddings when classical IR gets fiddly | Push through — the difficulty *is* the demonstration. Embeddings only as an optional comparison arm |
| Scope creeps into chemical process advice | Boundary in the design doc Week 3, enforced in prompts and schemas |
| Live hardware fails at evaluation | Simulator on identical MQTT topics; demo both, label clearly |
| Translation quality unverifiable by us | Native-speaker review of a sample; document the limitation; human sign-off mandatory |
| Uneven contribution surfaces at viva | Independently ownable slices, one directory each, cross-layer PR review |
| Late additions crowd out evaluation | LLM orchestrator and supervisor dashboard are explicitly **droppable** if evaluation isn't complete by end of Week 7 |

### 27. Deliberate Divergences From Lab Code

Name these in the report — unexplained divergence looks like error, explained divergence looks like judgement.

**Lab 02 strips all punctuation. We can't.** That destroys `78-93-3`, `1,2-dichloroethane`, `≤25 °C`. We protect chemical identifier patterns before punctuation removal and restore them after.

**Lab 03 splits on whitespace. We need a domain tokenizer.** `content.split()` fragments `2-butanone`. Same principle as Lab 02's own warning that documents and queries must share a tokenizer, applied to a harder vocabulary.

**Lab 02 stems everything. We stem selectively.** Stemming could collapse `chlorate` and `chloride` — two substances, very different hazards. Direct application of Lecture 2's over-normalisation warning, with a safety consequence attached.

### 28. The Two Things That Would Sink Us

**Deferring evaluation.** A system with no metrics table has no IR marks, however well it demos.

**Building beyond the labs before building the labs.** Get plain Lab 03 indexing and Lab 05 cosine ranking working on chemistry data in Week 4 — recognisably lab code, applied to our corpus. Then extend. A simple working system we extend is a project. An ambitious system that never quite works is a viva none of us can defend.

---

## Part XII — Decisions Needed Today

1. **Register Chemical Engineering** before slots fill. IoT is our technique, not our domain.
2. **Assign the four slices**, particularly M2 — heaviest and most heavily marked.
3. **Agree the scope boundary now** — retrieval and reconciliation only, no process advice.
4. **Agree the Week 4 baseline discipline** — lab code on our corpus first, extensions after.
5. **Agree the drop list** — LLM orchestrator and supervisor dashboard go if evaluation slips past Week 7.
