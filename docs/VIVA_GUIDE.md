# ChemSentry: Viva Preparation Guide

**Module:** IT3041 Information Retrieval and Web Analytics · **Domain:** Chemical Engineering (industrial chemical storage safety)

This guide covers what the system does, how each part works, who built which part, and the
questions the panel is likely to ask about each. Every claim here is traceable to code in
this repository; file paths are given so you can open the code during the viva.

---

## 1. The system in one paragraph

ChemSentry monitors chemical storage zones with temperature and humidity sensors. When a
reading arrives, it does **not** compare it against a number written into the code. Instead
it retrieves the applicable limit from the chemical's own Safety Data Sheet (SDS), checks
whether different suppliers' sheets disagree, and lets a **deterministic rule engine** decide
one of three states: **SAFE**, **WARNING** or **UNKNOWN**. Every WARNING becomes an alert that
an administrator must review and sign off before it is final. A language model is used only to
explain or translate a verdict that has already been decided. It never decides safety.

**Central principle (say it word for word if asked):**
> No safety threshold is ever hardcoded. Every threshold is retrieved from a versioned source
> document at query time and cited back to the user.

---

## 2. Architecture and data flow

```
 ESP32 + DHT22 sensor ──MQTT/TLS──► Agent C (environment monitor, no chemical knowledge)
                                          │  "Zone C is 15 °C; it stores H2O2 and KMnO4"
                                          ▼
 SDS PDFs ─► M1 pipeline ─► indexes ─► Agent A (retrieval: tolerant match → Boolean →
 (corpus/raw)  extraction,              index elimination → TF-IDF) → cited thresholds
               preprocessing                      │
                                                  ▼
                                   Evidence Reconciler (authority hierarchy, Jaccard, 5 % tolerance)
                                                  ▼
                                   Deterministic Safety Layer → SAFE / WARNING / UNKNOWN
                                                  ▼
                                   Agent B (severity classifier, Apriori + CAMEO, safety card)
                                                  ▼
                                   LLM (Mistral): explain / translate only
                                                  ▼
                                   Human sign-off (admin only, RBAC enforced on the server)
```

**How the agents talk to each other:** the agents run in one process and exchange typed Pydantic
models defined in `agents/protocols/schemas.py`. This is ADR 0005. MCP was considered and
rejected because of latency, determinism and deployment simplicity. If the panel asks "did you
use MCP?", the answer is: *planned, then deliberately replaced by in-process typed schemas.
See ADR 0005.*

### The three safety states

| State | Meaning | Rule (`safety/state_machine.py`) |
|---|---|---|
| SAFE | Reading is inside every retrieved limit | Not past any max/min threshold |
| WARNING | A retrieved limit is breached | `value >= max` or `value <= min` |
| UNKNOWN | Not enough or conflicting evidence | No threshold retrieved, or suppliers conflict |

UNKNOWN is a feature, not a failure. The system never assumes SAFE when evidence is missing.

---

## 3. Functionality summary (what a user can do)

| Function | Where in the UI | Backend route | Owner |
|---|---|---|---|
| Sign in with role (viewer / analyst / admin) | Sign-in page | `POST /auth/login`, `GET /me` | M4 |
| Live zone monitoring: temperature vessel, humidity dial, per-chemical checks | Live environment | `GET /zones` | M4 (UI), M2/M3 (evaluation) |
| Inject a sensor reading (same path as real hardware) | Live environment → Sensor simulator | `POST /zones/{id}/telemetry` | M4 |
| Storage-compatibility analysis (Apriori + CAMEO) | Live environment → Storage compatibility | `GET /zones/{id}/co-storage-check` | M3 |
| Search a chemical's SDS limits with citations (typo-tolerant) | SDS search | `POST /query` | M2 (+ M1 index) |
| Review and sign off WARNING alerts | Sign-off queue | `GET /alerts`, `POST /admin/sign-off` | M4 + M3 |
| Plain-language and Sinhala/Tamil safety card for an alert | Sign-off queue → Safety card | `POST /alerts/{id}/narrate` | M3 |
| Upload an SDS PDF into the corpus (extracted and indexed live) | Zones & documents | `POST /corpus/documents` | M1 pipeline, M4 route |
| Manage zones and inventory | Zones & documents | `POST /zones`, `POST/DELETE /zones/{id}/chemicals` | M4 |
| Manage users | Users | `GET/POST /users` | M4 |
| Audit trail of every action | Audit trail | `GET /audit-log` | M4 |
| Hazard-severity classification (API) | (API only) | `POST /classifier/severity` | M3 |
| Open-ended question answering with IR tools (API) | (API only) | `POST /query/open` | M3 |
| System health (DB + MQTT broker) | Status bar | `GET /health` | M4 |

---

## 4. Member contributions

| Member | GitHub | Owns | Labs |
|---|---|---|---|
| **M1** | @sadhifumer | `corpus/`, `extraction/`, `preprocessing/`, `indexing/` | 02, 03, 07, Lecture 11 |
| **M2** | Bimsara Yehan (@Bimsara-Yehan) | `agents/agent_a_retrieval/`, `evaluation/` | 04, 05, 06A |
| **M3** | @theyasassri | `agents/agent_b_analysis/`, `safety/` | 06B, 08, 09 |
| **M4** | Sahas Seneviratne (@sahasenevi) | `agents/agent_c_environment/`, `firmware/`, `api/`, `ui/`, `simulator/`, `marketing/` | 01, L12 |

---

### 4.1 M1: Acquisition, Extraction, Preprocessing and Indexing

**Role in one line:** turn raw SDS PDFs into structured, cited facts and searchable indexes.
Everything downstream depends on this.

#### a) Corpus acquisition (`corpus/`)
- **Crawler** (`corpus/crawler/`, Lecture 11): breadth-first crawler with a URL **frontier**
  (`frontier.py`, which also normalises URLs to avoid duplicates), and a policy gate (`policy.py`)
  that every request must pass:
  - **Domain allowlist**: the crawler can only contact explicitly allowed hosts.
  - **robots.txt** compliance, including `Crawl-delay`.
  - **Politeness delay**: 3 s per host by default.
  - **Redirects followed manually**, each hop re-checked, so a site cannot bounce the crawler
    to a disallowed host (SSRF protection).
  - Size cap (50 MB), page cap (20) and depth cap (2), so a crawl is provably bounded.
  - **Safe storage** (`storage.py`): file names come from a strict whitelist, never from the URL
    (path-traversal protection), and PDFs are verified by magic bytes.
- **PDF loader** (`pdf_loader.py`): reads local PDFs with `pdfplumber` (keeps reading order) and
  parses Section 1 metadata (chemical, supplier, CAS, version). It handles several supplier
  layouts: Sigma-Aldrich label:value, Carl Roth ("Identification of the substance X") and
  PanReac ("Trade name:X"). It also supports admin overrides saved beside the PDF
  (`<id>.meta.json`), so they survive restarts.
- **Ingestion audit** (`ingestion_audit.py`): `python -m corpus.ingestion_audit` fingerprints
  every PDF (SHA-256), runs it through the real extraction pipeline, and records what was read.
  - It classifies each file as new, changed, unchanged or removed since the last run, flags
    byte-identical duplicates and data-quality problems (no name, no supplier, no Section 7,
    no storage limit), and appends one event per change to an append-only JSON Lines log.
  - Every recorded value comes from the document or the pipeline; nothing is typed in.

#### b) Extraction (`extraction/`, Lab 07)
- `section_splitter.py`: splits an SDS into the **16 GHS sections**, so each extractor only
  reads the section where its value lives (Section 7 storage, 8 exposure/PPE, 9 properties,
  10 incompatibilities).
- `value_extractor.py`: regex extractors for storage temperature (min/max and range forms),
  humidity, CAS numbers, H/P-codes, exposure limits, PPE, flash and boiling points, and
  incompatible materials.
  - **ReDoS protection:** bounded quantifiers (`{0,N}` instead of `.*`) plus a 5-second regex
    timeout.
  - **Locale-aware numbers:** handles European `-17,0 °C` and `1.390 °C` (thousands
    separator).
  - **Supplier formats:** bare `<` / `>` comparators, a leading `+`, and `º` used as a degree
    sign (PanReac: "Minimum storage temperature:> 2ºC"). "Room Temperature" correctly extracts
    nothing, because it isn't a number.
- `normaliser.py`: unit conversion (°F→°C, ppm→mg/m³). Without it, "77 °F" and "25 °C" from
  two suppliers would look like a false conflict.
- `models.py`: Pydantic models (`SDSMetadata`, `ExtractionResult`, `ProcessedDocument`). Every
  extracted value carries **provenance**: document ID, supplier, revision, section and text
  span. A value without provenance cannot exist (Pydantic rejects it).

#### c) Preprocessing (`preprocessing/`, Lab 02): three documented divergences from the lab
1. **Domain tokenizer** (`tokenizer.py`): protects CAS numbers (`78-93-3`), chemical prefixes
   (`1,2-dichloroethane`), value+unit (`25 °C`), H/P-codes and formulas before splitting. The
   lab's `.split()` would break `78-93-3` into `78`, `93`, `3`.
2. **Stop words that keep negation** (`stopwords.py`): `not`, `no`, `never` and `without` are
   kept, because "Do NOT store near oxidisers" must not become "store near oxidisers". SDS
   boilerplate (`section`, `page`, `version`) is removed.
3. **Selective stemming** (`stemmer.py`): Porter stemming for general English, but chemical
   suffixes (`-ate`, `-ide`, `-ite`, `-ol`, `-one`, `-ene`, `-ane`, `-ine`, `-yl`, `-oxy`) and any
   token containing digits are protected, so **chlorate ≠ chloride**.
- `pipeline.py`: documents and queries go through the **same** pipeline. This is Lab 02's core
  invariant.

#### d) Indexing (`indexing/`, Lab 03)
- `inverted_index.py`: hand-built term → postings (doc, frequency). Supports Boolean AND, OR
  and NOT.
- `positional_index.py`: stores term positions for **phrase** ("store below") and **proximity**
  ("storage /3 temperature") queries.
- `index_builder.py`: builds the inverted, positional and **k-gram** indexes (the k-gram index
  feeds M2's tolerant matching). It also supports incremental updates when a new SDS is
  uploaded.

#### M1 evidence (Layer 3 evaluation, `evaluation/results/layer3_extraction_quality.md`)
Precision 1.00, recall 1.00 and F1 1.00 over 28 claims (CAS, flash point, boiling point,
storage min/max) on the real corpus. Fields that genuinely have no number in the SDS (for
example "see product label") are correctly extracted as nothing; these are the true negatives.

#### Likely questions for M1
- **Why hand-build the inverted index instead of using Whoosh, Lucene or sklearn?** It *is* the
  Lab 03 deliverable. A library would show nothing from the syllabus, and hand-building lets
  us control tokenisation for chemical identifiers.
- **Why regex and not an LLM for extraction?** Extraction is on the safety path. A regex that
  fails visibly (extracts nothing, which leads to UNKNOWN) is safer than an LLM that fails
  silently with a plausible wrong number.
- **What is ReDoS and how do you prevent it?** Catastrophic backtracking from nested or
  unbounded quantifiers on hostile input. We use bounded quantifiers and a timeout.
- **Why a positional index as well?** "store below 25 °C" only means something if the words
  are adjacent; a plain inverted index cannot tell.
- **How is the crawler a good citizen and secure?** Allowlist, robots.txt, 3 s politeness,
  manually re-checked redirects, size caps and whitelisted file names.
- **What happens when an SDS has no storage temperature?** Nothing is extracted, Agent A
  returns no threshold, and the safety layer returns UNKNOWN. This is the honest result.
- **How do you know which SDS versions were in force?** The ingestion audit log. Each file's
  SHA-256 plus what was extracted is recorded on every new, changed or removed event.

---

### 4.2 M2: Retrieval (Agent A) and Evaluation

**Role in one line:** given a (possibly misspelled) chemical name, find the right SDS and
return cited thresholds fast.

#### Agent A (`agents/agent_a_retrieval/`)
- **Tolerant matching cascade** (`tolerant_match.py`, Lab 04):
  1. exact match;
  2. **k-gram** candidate narrowing (`kgram_index.py`, hand-built) + **Levenshtein** edit
     distance (`nltk.edit_distance`);
  3. **Soundex** phonetic fallback (`soundex.py`, hand-built), for example "ksylene" → "xylene".
- **Wildcard queries** (`wildcard_match.py`): prefix and suffix patterns (`*acid`, `per*`).
  These are retrieval only, never classification. A suffix never implies a hazard class.
- **Index elimination** (`index_elimination.py`, Lab 06A): uses only high-IDF query terms plus
  a set-overlap pre-filter, which shrinks the candidate set before ranking.
- **TF-IDF + cosine ranking** (`tfidf_ranker.py`, Lab 05): sklearn `TfidfVectorizer`, the
  technique the lab teaches.
- **Source authority** (`source_authority.py`): which source to trust for which question (for
  example supplier SDS for storage, NIOSH for exposure limits).
- **Provenance bridge** (`provenance_bridge.py`): converts M1's `ExtractionResult` into the
  `ProvenancedThreshold` the safety layer consumes. This is the link that makes "full
  provenance" true end to end.
- **Entry point** (`corpus_retrieval.py`): `CorpusRetriever.get_thresholds(name)`.

#### Evaluation suite (`evaluation/`): five layers
| Layer | Measures | Headline result |
|---|---|---|
| 1 Retrieval quality | P@5, R@10, MAP, latency per configuration | With tolerant matching: P@5 0.46, R@10 0.90, **MAP 0.85** (Boolean-only MAP 0.49) |
| 2 Entity resolution | exact / misspelled / wildcard name resolution | **30/30 pass** (F1 1.00 in every category) |
| 3 Extraction quality | precision/recall of extracted claims (M1) | F1 1.00 on 28 claims |
| 4 Conflict detection | numeric 5 % tolerance + Jaccard hazard conflicts (M3) | 10/10 scenarios correct |
| 5 End-to-end state accuracy | SAFE/WARNING/UNKNOWN vs ground truth | **16/16 (100 %)** |

Layers 1, 3 and 5 need the real PDFs in `corpus/raw/`.

#### Likely questions for M2
- **Why not vector embeddings or a vector DB?** They are non-deterministic and opaque. Safety
  specs need exact token-level matching (1,2- vs 1,1-dichloroethane), and classical IR gives
  auditable scores and maps to the labs. Embeddings are allowed only as a comparison arm.
- **Why use sklearn for TF-IDF but hand-build the k-gram index?** Lab 05 teaches
  `TfidfVectorizer`. The hand-built deliverables are the index structures (Labs 03/04).
- **What does index elimination trade?** A little relevance for speed. Layer 1 shows MAP
  barely changes (0.64 → 0.65), which justifies it on the live alert path.
- **Why does P@5 look low?** Many queries have only one or two relevant documents in a
  13-document corpus, so P@5 is capped. MAP and R@10 are the meaningful numbers here.
- **How does the system fix "hydrogen peroxde"?** k-gram overlap narrows the candidates, and
  Levenshtein distance 1 then picks "hydrogen peroxide".

---

### 4.3 M3: Analysis (Agent B), Reconciliation and the Safety Layer

**Role in one line:** decide the safety state deterministically, reconcile conflicting
evidence, and add analysis (severity, co-storage, explanations).

#### Safety layer (`safety/`)
- `state_machine.py`: `DeterministicSafetyEvaluator` returns SAFE, WARNING or UNKNOWN. **No LLM
  on this path** (ADR 0002).
- `reconciliation_policy.py`: a *versioned* policy (v1.0.0) for reconciliation parameters:
  **5 % numeric conflict tolerance** and **Jaccard ≥ 0.6** for hazard agreement. Even these are
  not hardcoded in the logic; they carry a version, rationale and citation, and every alert's
  reasoning ends with `[policy_version=1.0.0]`.
- `provenance.py`: citation generator and supplier trust tiers.

#### Agent B (`agents/agent_b_analysis/`)
- **Evidence reconciler** (`reconciler.py`, Lab 06B): picks the governing source using the
  authority hierarchy. If equal-authority sources diverge by more than 5 %, it flags a conflict
  and the state becomes UNKNOWN. It also compares hazard-code sets with **Jaccard similarity**:
  we invert the crawler's near-duplicate idea to *surface* differences rather than discard them.
- **Severity classifier** (`classifier.py`, Lab 08): `DecisionTreeClassifier` with
  `class_weight='balanced'`, predicting LOW / MEDIUM / HIGH / CRITICAL from NFPA ratings and GHS
  counts. The NFPA values are supplied by the caller because no SDS in the corpus contains
  parseable NFPA ratings.
- **Apriori co-storage** (`apriori_discovery.py`, Lab 09): `mlxtend.apriori` over zone
  inventories finds chemicals *stored together*. **Apriori finds patterns, not hazards**: every
  pair is checked against a CAMEO reactivity lookup grounded in real SDS Section 10 data (for
  example NaOH + H₂SO₄ is a violent reaction).
- **LLM layer** (`llm_layer.py`, Mistral, ADR 0003): `SafetyCardNarrator` explains alerts and
  translates them to **Sinhala / Tamil**. The verdict field is always copied from the
  deterministic result, so a mistranslation cannot change it. It falls back to the
  deterministic reasoning when no API key is set.
- **Query orchestrator** (`query_orchestrator.py`): for open questions, the LLM chooses which
  classical IR tools to call. It routes; it does not decide safety.
- `chat_fast_path.py`: a gated prototype, deliberately not exposed in the API.

#### Evidence
Layer 4: 10/10 conflict scenarios. Layer 5: 16/16 end-to-end states. Classifier
(`severity_classifier_metrics.md`): CRITICAL-class F1 is 0.333 with `balanced` vs 0.000
without. This is why class weighting matters: accuracy alone (0.96) hides minority-class
failure.

#### Likely questions for M3
- **Why can't the LLM decide whether it's dangerous?** LLMs are non-deterministic and can
  hallucinate. A hallucinated SAFE during a breach is catastrophic. See ADR 0002.
- **What happens when two suppliers disagree?** Higher authority wins. If authorities are equal
  and the values differ by more than 5 %, the state is UNKNOWN and the conflict is shown to the
  user.
- **Why is the CRITICAL F1 low?** Very few CRITICAL samples (24 in total). Balanced weighting
  is the documented mitigation; more labelled data is the real fix.
- **Known limitation to admit honestly:** the CAMEO lookup only covers pairs backed by SDS
  Section 10 text in our corpus. For example HCl + NaOH shows "no CAMEO warning" even though an
  acid and a base do react. The rule table needs extending, which is why the output is labelled
  as evidence, not a verdict.

---

### 4.4 M4: Agent C, IoT, API, Security and UI

**Role in one line:** get real sensor data in, expose everything through a secure API, and
give people a usable interface.

- **Agent C** (`agents/agent_c_environment/monitor.py`): knows each zone's reading and its
  inventory but holds **no thresholds**. For every reading it must ask Agent A. This
  constraint is what makes the design genuinely multi-agent.
- **IoT path:** ESP32 + DHT22 firmware (`firmware/src/main.cpp`) publishes to
  `chemsentry/sensors/<zone>/reading` over **MQTT/TLS** (Mosquitto, per-device certificates from
  `firmware/generate_certs.py`). `mqtt_http_bridge.py` forwards readings to the API.
  `simulator/telemetry_simulator.py` stands in for hardware.
- **API gateway** (`api/main.py`, FastAPI): JWT auth (HS256, 24 h), **RBAC enforced on the
  server**. A forged sign-off from a viewer gets HTTP 403, which was verified in testing.
  Passwords are hashed with bcrypt.
- **Encryption at rest** (ADR 0004): alert and audit-log fields are encrypted with Fernet,
  which works on both SQLite and PostgreSQL.
- **Secure SDS upload:** PDF validation, safe file names and admin-only access.
- **Audit trail:** append-only log of alert creation, sign-off and admin actions.
- **UI** (`ui/`, React + Vite + Motion): Live environment, SDS search, Sign-off queue, and the
  Users / Zones & documents / Audit trail admin pages.

#### Likely questions for M4
- **Why does Agent C have no chemical knowledge?** It forces retrieval on every reading, so no
  threshold can sneak into the monitoring code.
- **How is the IoT link secured?** TLS with per-device certificates, and the broker rejects
  unknown devices.
- **Why is RBAC enforced on the backend and not just hidden in the UI?** Hiding a button is not
  security. The API itself returns 403.
- **Why three roles?** Separation of duties. The analyst who submits data is not the authority
  who closes a safety alert.

---

## 5. Responsible AI: answers to have ready

| Concern | Answer |
|---|---|
| Transparency | Every limit shows supplier, SDS ID and section; every alert carries the reasoning and policy version |
| LLM risk | LLM is isolated from the decision path; the verdict is copied, never generated |
| Uncertainty | UNKNOWN instead of a guess; missing or conflicting evidence forces human review |
| Accountability | Mandatory admin sign-off with notes; append-only, encrypted audit trail |
| Fairness / access | Sinhala and Tamil safety cards for floor staff |
| Privacy | Sensors send only physical values (no worker data); RBAC; encryption at rest |
| Misuse | Scope limited to storage safety; no synthesis or reaction guidance |

---

## 6. Live demo script (5 minutes)

1. Sign in as **admin_user**. Explain the three roles and why only admins sign off.
2. **Zones & documents** → upload an SDS PDF. *"Extraction, preprocessing and indexing run now,
   with no restart."* (M1)
3. **SDS search** → type a misspelling such as `hydrogen peroxde`. Show the corrected match,
   the 2–8 °C limits with citations, and click the pipeline stages. (M2)
4. **Live environment** → Zone C → set 15 °C → **Transmit reading**. The vessel fills amber
   past the MAX line, the zone turns WARNING, and the sign-off badge appears. (M4 → M2 → M3)
5. Point at **Storage compatibility** on Zone B: NaOH + H₂SO₄ flagged as a violent reaction,
   explained as *Apriori pattern plus CAMEO lookup*. (M3)
6. **Sign-off queue** → open the alert → **Safety card** in Sinhala → approve with a note. (M3 + M4)
7. **Audit trail**: show "Alert created" and "Sign off" entries. (M4)
8. Finish on **Zone A → UNKNOWN**: Ethanol (Carl Roth, 15–25 °C) and 2-Propanol (PanReac,
   2–25 °C) are both within range, but Acetone's SDS states no numeric limit ("see product
   label"). *"One chemical without evidence keeps the zone UNKNOWN; we refuse to call it SAFE."*
9. In a terminal, run `python -m corpus.ingestion_audit --dry-run` to show the corpus trail. (M1)

---

## 7. Numbers to remember

- 3 states, 3 agents, 3 roles, 16 GHS sections, 5 evaluation layers.
- MAP 0.85 (tolerant matching) vs 0.49 (Boolean only).
- Entity resolution 30/30; extraction F1 1.00; conflict detection 10/10; end-to-end 16/16.
- Reconciliation policy v1.0.0: 5 % numeric tolerance, Jaccard 0.6.
- Test suite: 301 passed, 1 skipped (`pytest tests/`); black and ruff clean.
- ADRs: 0002 LLM isolated from safety, 0003 Mistral, 0004 encryption at rest, 0005 in-process
  typed protocols.

---

## 8. Open issues found during verification (for each owner to fix)

These were found while testing everyone's features end to end. **None of them were changed
in the teammates' code**; each owner should decide the fix. Being able to name these yourselves is
stronger in a viva than having them found by the panel.

| Owner | Where | Issue | Why it matters |
|---|---|---|---|
| **M2** | `agents/agent_a_retrieval/corpus_retrieval.py` `get_thresholds` (uses `tolerant_match.resolve`) | **Cross-chemical match.** A chemical with no SDS of its own can resolve to a *different* chemical and inherit its limits. Both fuzzy stages do it: Soundex ("Hydrochloric acid" → "hydrogen peroxide solution", both code **H362**; also Hydroquinone and Hydrazine), and the edit-distance step ("Methanol" → "Ethanol", "Ethanolamine" → "Ethanol"). Example: with no HCl SDS, Zone B shows a false WARNING at 20 °C from hydrogen peroxide's 2–8 °C limit. | A chemical silently borrows another chemical's threshold, which contradicts "never fabricate". Refusing Soundex-only matches would not be enough on its own, because edit distance causes it too. **Bimsara (M2) is fixing this in a separate PR**; update this row when it lands. |
| **M4** | `api/main.py` `_seed_initial_zone_readings` (~line 215) and `create_zone` (~line 1083) | Every zone gets an invented **20 °C / 45 %** reading (`device_id: startup-default`) at startup and on creation. | The dashboard shows a reading no sensor took, and it is evaluated as if real. |
| **M3** | `agents/agent_b_analysis/apriori_discovery.py` `KNOWN_INCOMPATIBLE_PAIRS` | Reactivity verdicts come from a fixed dictionary of exact pairs. A pair not listed (e.g. HCl + NaOH) comes back "COMPATIBLE", and so does any group of three or more, even one that contains a reactive pair. | Adding an SDS can never raise a new warning. M1 already extracts Section 10 "incompatible materials" with citations, which could drive this instead. The UI now shows "COMPATIBLE" as a neutral "No known warning on file" and lists pairs only, so it never looks safer than the evidence. |
| **M4** | `api/main.py` `upload_sds_document` | SDS uploads write no entry to the API audit log (only `alert_created` and `sign_off` are logged). User and zone changes aren't logged either. | Use `python -m corpus.ingestion_audit` for the corpus trail meanwhile. |
| **M4** | `api/security.py` `_get_demo_users` | Demo accounts (published passwords) also authenticate when `CHEMSENTRY_ENV=production`. | Should be disabled outside development. |
| **M4** | `agents/agent_c_environment/mqtt_http_bridge.py` `--password` default | The analyst password is a built-in default. | Prefer an environment variable. |
| **M4** | `firmware/src/main.cpp` `ZONE_ID` / `MQTT_TOPIC` | The zone is hardcoded as `Zone_C`. | Every device built from this source reports as Zone C. Could move to `secrets.h`. |
| **M4** | `simulator/telemetry_simulator.py` `_EXCURSION_TEMP_C = 18.0` | The excursion value was chosen to exceed Zone C's 2–8 °C limit. | Fine for a demo; an explicit `--excursion-temp` flag would avoid tying it to one chemical. |

