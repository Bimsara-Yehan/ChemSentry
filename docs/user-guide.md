# ChemSentry — User Guide

This guide explains what ChemSentry does, why it has three user roles, what each screen
is for, and how the pieces underneath the UI — sensors and Safety Data Sheets — actually
feed into what you see. It's written for anyone trying to *use* the running system
(team members, evaluators, viva panel) rather than anyone editing its code.

---

## 1. What ChemSentry does, in one paragraph

ChemSentry watches chemical storage zones (temperature/humidity sensors) and, whenever a
reading looks unusual, automatically retrieves the relevant safety limit from the
chemical's actual Safety Data Sheet (SDS) — a real supplier PDF, not a number typed into
the code — and decides whether the situation is **SAFE**, a **WARNING**, or **UNKNOWN**
(meaning: not enough evidence to say either way). A human (an admin) still has to review
and sign off every WARNING before it counts as a confirmed alert. The system never makes
that final call on its own, and it never guesses a safety limit — every number it shows
you is retrieved from a document and cited.

---

## 2. Why three user roles? (Viewer / Analyst / Admin)

This isn't an arbitrary demo of "RBAC exists." It maps onto a real constraint in the
system's design: **a WARNING is not allowed to become a final alert without a human
sign-off** (see `CLAUDE.md`'s architecture — "Human sign-off (RBAC-gated, mandatory
before any alert is final)"). Once you accept that one role must be able to make that
final call, three tiers fall out naturally from *who else touches the system and what
they're trusted to do*:

| Role | Real-world analogue | What they're trusted to do | Why |
|---|---|---|---|
| **Viewer** | An auditor, trainee, or plant manager who needs visibility but shouldn't be able to change anything | Read zone status, alerts, and history only | You want people to be able to check compliance status without being able to (accidentally or otherwise) inject a reading or wave through an alert |
| **Analyst** | A lab technician / EHS analyst doing day-to-day work | Everything a viewer can do, plus: submit telemetry readings and query the retrieval system for a chemical's safety data | This is the "normal operation" role — someone who feeds data in and looks things up, but isn't the one accountable for the final safety decision |
| **Admin** | The Safety Officer / supervisor of record | Everything an analyst can do, plus: approve or reject a WARNING alert | Separation of duties — the person(s) submitting readings and running queries should not be the same authority that closes out a safety alert. This is what actually makes "mandatory human sign-off" mean something rather than being a rubber stamp |

The key design point: **only the sign-off action is admin-gated.** Viewer vs. analyst is
about whether you can *act* on the system at all (submit data, query it); analyst vs.
admin is specifically about who is allowed to *close out a safety decision*. That split
is enforced on the backend (`api/main.py`), not just hidden in the UI — a viewer who
somehow forged a query request would still be rejected with an HTTP 403.

---

## 3. Logging in

Three demo accounts exist for the three roles:

| Username | Password | Role |
|---|---|---|
| `viewer_user` | `viewer123` | Viewer |
| `analyst_user` | `analyst123` | Analyst |
| `admin_user` | `admin123` | Admin |

After logging in, look at the **role banner** just below the navigation tabs — it tells
you in plain language what your current account can and can't do. This is the fastest
way to tell the three roles apart; the tabs themselves look the same for everyone (the
data you can *see* is the same for all roles — only what you can *do* changes).

---

## 4. The three tabs, and what each is for

### Tab 1 — Live Environment

**What it's for:** monitoring the current state of each storage zone in real time.

- **Zone selector** (Zone A / B / C chips) — switch which storage zone you're looking at.
  Each zone represents a physically separate storage area with its own chemical
  inventory:
  - **Zone A — Solvent Storage:** Ethanol, 2-Propanol, Acetone
  - **Zone B — Acid & Base Storage:** Sodium hydroxide, Hydrochloric acid, Sulfuric acid
  - **Zone C — Oxidizer Storage:** Hydrogen peroxide solution, Potassium permanganate
- **Zone Telemetry card** — shows the most recent temperature/humidity reading for the
  selected zone, plus an overall safety-state badge (SAFE / WARNING / UNKNOWN) and a
  breakdown per chemical explaining *why* — e.g. "Ethanol — max_storage_temperature:
  SAFE" with the reasoning underneath.
- **Chemicals Stored in This Zone card** — the zone's inventory list.
- **Send a Test Reading** (viewers can't use this) — since the physical ESP32 sensors
  don't publish live data yet (see §5 below), this panel lets an analyst or admin submit
  a reading manually and immediately see the real safety evaluation it produces. It's not
  a fake preview — it calls the same evaluation pipeline a real sensor reading would.

**Why some zones never turn WARNING or SAFE, only UNKNOWN:** this is expected, not a
bug. Of all the chemicals seeded in this demo, only **Hydrogen peroxide solution**
(Zone C) has a real, numeric storage-temperature limit extracted from its actual SDS in
this project's corpus. Every other chemical's real SDS either has no such field or just
says "see product label" with no number. Per the system's central rule — *never force a
SAFE/WARNING verdict when evidence is missing* — Zones A and B will honestly report
UNKNOWN for temperature checks regardless of the reading you send, because there's
genuinely no retrievable threshold to check it against. That's the system refusing to
fabricate a number it doesn't have.

### Tab 2 — Retrieval & Reconciliation

**What it's for:** looking up what the system actually knows about a specific chemical,
independent of any zone or sensor reading.

- Type a chemical name (e.g. `Ethanol`, `Sodium hydroxide`) and hit **Search**. This runs
  the same retrieval pipeline described in §6 below and returns:
  - The overall safety state for that chemical.
  - Every **retrieved threshold** found for it, each with a **citation** (which document,
    which section) — this is the "no hardcoded thresholds" principle made visible: you
    can see exactly where every number came from.
  - Any **supplier conflicts** — if two different suppliers' SDS documents disagree on a
    hazard classification for the same chemical, that's flagged here instead of silently
    picking one.
- The **How This Works** panel on the right names the specific classical information-
  retrieval techniques behind the search (inverted index, tolerant/fuzzy matching,
  TF-IDF ranking, conflict detection) — useful context if you're explaining the system to
  someone else, not something you need to interact with.

### Tab 3 — Sign-Off Queue

**What it's for:** the human-in-the-loop safety gate. Every time a WARNING is produced
(either from a live/simulated reading or automatically when an excursion is detected),
it shows up here as a pending alert.

- Each alert card shows the observed value vs. the retrieved threshold it violated, and
  the full reasoning behind the WARNING.
- **Only admin accounts** see Approve/Reject buttons and a notes field. Everyone else
  sees "Awaiting admin sign-off." Once resolved, the card shows who signed off and what
  note they left — this is the audit trail.

---

## 5. How the IoT sensors connect to this

The intended data path (from `CLAUDE.md`'s architecture) is:

```
ESP32 + DHT22/MQ-135 sensor  →  MQTT (TLS)  →  Agent C  →  Agent A + Safety Layer  →  UI
```

Concretely:
1. Each physical sensor node reads temperature, humidity, and a gas value, and is meant
   to publish it over MQTT (TLS-secured, via Mosquitto) to a topic like
   `chemsentry/sensors/Zone_A/reading`.
2. **Agent C** (`agents/agent_c_environment/mqtt_subscriber.py`) subscribes to those
   topics. It deliberately holds **no chemical knowledge of its own** — it doesn't know
   what a safe temperature is. All it knows is *which chemicals are stored in which
   zone*.
3. For every reading, Agent C asks Agent A (the retrieval system) to look up the
   relevant threshold for each chemical in that zone, then hands the reading and the
   retrieved threshold to the deterministic safety layer, which returns SAFE / WARNING /
   UNKNOWN with a reasoning string.
4. That result is what populates the Live Environment tab, and — if it's a WARNING —
   creates an entry in the Sign-Off Queue.

**Current state of the real hardware:** the firmware (`firmware/src/main.cpp`) reads the
DHT22 and gas sensor and displays them on an LCD, but **does not yet publish over MQTT**
— that wiring hasn't been completed. Because of that, the **Send a Test Reading** button
on the Live Environment tab exists to stand in for a real sensor: it calls the exact same
backend evaluation path a real MQTT-published reading would, just triggered manually
instead of from hardware. Nothing about the evaluation logic is different — only the
trigger.

---

## 6. How the SDS documents connect to this

Every number the UI ever shows you traces back to an actual PDF, through this pipeline:

```
Real SDS PDFs (corpus/raw/)
  → Extraction (regex-based parsing of storage limits, GHS codes, CAS numbers, etc.)
  → Preprocessing & Indexing (tokenizing, inverted index, k-gram index for fuzzy matching)
  → Agent A retrieval, when you search or a zone gets evaluated:
      tolerant matching (handles typos/misspellings)
      → Boolean filtering
      → index elimination (fast narrowing on a large corpus)
      → TF-IDF ranking (best-matching document(s) for the query)
  → Evidence Reconciler (if multiple supplier documents exist for the same chemical:
      picks the most authoritative source, flags disagreements via Jaccard similarity)
  → Deterministic Safety Layer (compares the retrieved number against the reading;
      returns SAFE / WARNING / UNKNOWN — never guesses, never uses an LLM for this step)
```

This is why the Retrieval tab always shows a **citation** next to every value, and why
the system says **UNKNOWN** instead of inventing an answer when a chemical's SDS simply
doesn't contain a number for the metric being checked (see the Zone A/B example in §4).
The LLM only ever gets involved *after* this whole process — to summarize or translate
the result into plain language — never to decide the safety state itself.

---

## 7. Common tasks

**"Is a zone currently safe?"**
→ Live Environment tab → pick the zone → look at the safety-state badge on the
Temperature card.

**"What's the storage limit for a specific chemical, and where does that number come
from?"**
→ Retrieval & Reconciliation tab → search the chemical name → read the retrieved
threshold and its citation.

**"I want to see what happens during a temperature excursion (without real hardware)."**
→ Live Environment tab → pick a zone → click "Send Excursion Reading" (requires
analyst/admin) → watch the safety state update, then check the Sign-Off Queue for the
resulting alert.

**"I need to approve or reject a pending alert."**
→ Log in as `admin_user` → Sign-Off Queue tab → review the reasoning → Approve or
Reject, optionally with a note.

**"Why does this zone always say UNKNOWN no matter what I send?"**
→ See §4 — it means the real SDS documents for that zone's chemicals genuinely don't
contain a numeric value for the metric being checked. This is correct, conservative
behavior, not a broken feature.

---

## 8. Known limitations (worth knowing before a demo)

- **Firmware doesn't publish over MQTT yet.** The "Send a Test Reading" button is a
  stand-in that exercises the real evaluation pipeline, but no physical sensor is
  currently feeding it automatically.
- **Zone inventory is manually seeded**, not live-crawled from a real facility's
  inventory system — see `agents/agent_c_environment/zone_inventory.py` for exactly
  which chemicals are assigned to which zone and why.
- **Only Hydrogen peroxide (Zone C)** can currently produce a genuine SAFE/WARNING
  temperature result from this project's corpus; Zones A and B will stay UNKNOWN for
  temperature checks until SDS documents with real storage-temperature fields for their
  chemicals are added to `corpus/raw/`.
