# ChemSentry: Operations Guide

How to install, start and use ChemSentry: **what** to do, **how** to do it, and **why** each
step exists. Commands are for Windows PowerShell, run from the repository root
(`ChemSentry/`) unless stated otherwise.

---

## 1. One-time setup

### 1.1 Prerequisites
| Tool | Version | Why |
|---|---|---|
| Python | 3.11+ | Backend, agents, evaluation |
| Node.js | 20+ | React UI (Vite) |
| Git | any | Source control |
| Docker Desktop | optional | Mosquitto MQTT broker and PostgreSQL for the full IoT setup |

### 1.2 Install
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd ui
npm install
cd ..
```
*Why:* the pinned `requirements.txt` guarantees the same library versions as CI (an unpinned
FastAPI once broke CI silently).

If PowerShell refuses to run `Activate.ps1`, allow scripts for the current window only:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

### 1.3 Configuration (optional for local use)
Copy `.env.example` to `.env` only if you need to change defaults:
- `DATABASE_URL`: defaults to a local SQLite file, so nothing is required for development.
- `MISTRAL_API_KEY`: enables the plain-language explanations and Sinhala/Tamil safety cards.
  Without it the system still works and shows the deterministic reasoning instead.
- `JWT_SECRET_KEY` and `CHEMSENTRY_DATA_KEY`: generated automatically in development, but
  **required** in production.

### 1.4 Load Safety Data Sheets
The SDS PDFs are deliberately **not in Git** (`corpus/raw/` is gitignored). Without them every
chemical reports **UNKNOWN**, because there is no evidence to judge against.

You can add PDFs in either of two ways:
- **Before starting:** copy the PDFs into `corpus/raw/`. They are loaded at startup.
- **While running:** sign in as admin, open **Zones & documents → Upload SDS**. The PDF is
  extracted and indexed immediately, with no restart.

### 1.5 Audit the corpus after adding SDSs
Whenever PDFs are added to, replaced in or removed from `corpus/raw/` (for example SDSs a
teammate shares with you), run:
```powershell
python -m corpus.ingestion_audit
```
- **What it does:** fingerprints each PDF (SHA-256) and runs it through the real extraction
  pipeline. It reports, per document, the chemical, supplier, CAS number, sections found and
  storage limits (with the source text). It flags problems such as "Section 1 gave no chemical
  name", "no storage-temperature limit extracted" or "byte-identical to another file".
- **Each run** classifies files as **new**, **changed**, **unchanged** or **removed** since the
  last run, and appends one event per change to `corpus/raw/.ingestion_audit.jsonl`. The log is
  append-only and gitignored, like the PDFs.
- **Options:** `--dry-run` reports without writing, `--json` gives machine-readable output, and
  `--actor <name>` records who ran it.
- **Why:** documents in `corpus/raw/` drive safety decisions the moment they're loaded. This
  gives a trail of exactly which document versions were in force and what was read from them.

---

## 2. Starting the system

Open **two terminals**.

**Terminal 1: backend API**
```powershell
.\.venv\Scripts\Activate.ps1
uvicorn api.main:app --reload --port 8001
```
API documentation is at http://localhost:8001/docs.

> Port 8001 is used because another program (Apache/XAMPP `httpd`) occupies 8000 on this
> machine. The error `[WinError 10013] An attempt was made to access a socket...` means the
> port is already in use, often by a server you started earlier. Close that terminal or pick
> another port.

**Terminal 2: frontend UI**
```powershell
cd ui
$env:VITE_API_BASE_URL="http://localhost:8001"
npm run dev
```
Open http://localhost:5173.

*Why the variable:* the UI defaults to port 8000; `VITE_API_BASE_URL` points it at the
backend's real port. It must be set in the **same terminal** before `npm run dev`.

---

## 3. Signing in and roles

| Username | Password | Role | Can do |
|---|---|---|---|
| `viewer_user` | `viewer123` | Viewer | See zones, alerts and history (read-only) |
| `analyst_user` | `analyst123` | Analyst | Viewer, plus send readings and search the SDS corpus |
| `admin_user` | `admin123` | Admin | Analyst, plus sign off alerts and manage users, zones, documents and the audit trail |

*Why three roles:* separation of duties. The person feeding data in should not be the person
who closes a safety alert. Restrictions are enforced by the server (a forged request gets
HTTP 403), not only hidden in the UI.

**Sessions:** refreshing the page keeps you signed in and on the same page. Closing the tab
signs you out, and a new tab asks you to sign in again. This is intentional for a shared safety
workstation. Sessions also expire after 24 hours; you will be returned to sign-in with a
message.

These demo accounts are for development only. Create real accounts under **Users** and do
not use the demo passwords in any shared deployment.

---

## 4. Using each screen

### 4.1 Live environment (all roles)
**What:** the current state of each storage zone.

**How to read it:**
- **Zone cards** (top): one per zone, with its latest temperature, number of chemicals and a
  status dot (green SAFE, amber blinking WARNING, grey UNKNOWN). Click a card to open the zone.
- **Vessel gauge:** the liquid level is the latest temperature. Dashed **MAX** (red) and
  **MIN** (blue) lines are drawn only when a limit was retrieved from an SDS. No lines means no
  limit is on file.
- **Humidity dial:** shown for information. It is not evaluated because no SDS in the corpus
  states a humidity limit.
- **Stored chemicals:** one tile per chemical, coloured by that chemical's own checks.
  Click a tile to see the exact evaluation trace (what was compared, against which limit, from
  which document).
- **Storage limits by source:** table of each limit with its supplier, SDS ID and section.
- **Storage compatibility** (right column): Agent B's co-storage analysis.
  - Apriori lists pairs of chemicals that are stored together, with support, confidence and
    lift.
  - Each pair is checked against Agent B's reactivity lookup, and the backend's status is shown
    as the tag, for example **Violent reaction** for sodium hydroxide + sulfuric acid.
  - A pair the lookup doesn't list is tagged **No known warning on file** in a neutral colour,
    never green: missing evidence is not a confirmation that the pair is safe.
  - Only pairs are shown. The lookup checks exact pairs, so its answer for a group of three or
    more says nothing about the pairs inside it.
  - *Why it's worded that way:* Apriori finds patterns, not hazards. The hazard label comes
    only from the reactivity lookup.

**Why a zone can stay UNKNOWN:** if a chemical's SDS has no numeric storage limit, the system
will not assume the reading is safe. Add an SDS that contains the limit and the zone becomes
evaluable.

### 4.2 Sensor simulator (analyst and admin)
**What:** sends a reading through exactly the same path as a real ESP32 sensor.

**How:**
1. Select the zone.
2. Set **Temperature** and **Humidity** with the sliders, or use a preset. The presets are
   computed from the zone's retrieved SDS limits (inside the range, just above the maximum, just
   below the minimum). A zone with no limit on file shows no presets.
3. Press **Transmit reading**.

**What happens:** Agent C receives the reading, asks Agent A for each chemical's limits, and the
deterministic safety layer decides the state. A WARNING creates an alert in the Sign-off queue
and shows a notification on every other page.

*Example:* Zone C stores hydrogen peroxide, whose SDS states 2–8 °C. Sending 15 °C gives a
WARNING; sending 5 °C gives SAFE.

### 4.3 SDS search (analyst and admin)
**What:** look up what the corpus says about a chemical, independent of any sensor.

**How:**
1. Type a name (misspellings are fine, for example `sodum hydroxide`), or click an inventory
   chip.
2. Press **Retrieve**.

**Result:**
- Every retrieved limit as a card with its value and source (supplier · SDS ID · section).
- Supplier conflicts, if two documents disagree.
- The badge says **Lookup only**: a search has no sensor reading, so it never produces a
  SAFE/WARNING verdict.

**Retrieval pipeline panel:** the five stages light up while a search runs. Click a stage to
read how it works (useful when explaining the system).

### 4.4 Sign-off queue (all roles; actions are admin only)
**What:** the human-in-the-loop gate. No WARNING is final until an admin signs it off.

**How:**
1. Use the four tiles (Awaiting review / Approved / Rejected / Total) to filter.
2. Click an alert to expand it. You will see who raised it and when, the cited source, the full
   reasoning, and a bar showing how far the reading exceeded its limit.
3. **Safety card** (optional): choose English, සිංහල or தமிழ், then press **Generate**.
   - You get a plain-language explanation for floor staff.
   - The verdict badge always comes from the deterministic layer, never from the language model.
   - Without `MISTRAL_API_KEY` the card shows the deterministic reasoning and says so.
4. **Admin only:** add a sign-off note (what was checked and what action was taken), then
   **Approve** (genuine excursion, handled) or **Reject** (false alarm, for example a faulty
   sensor).

**Why notes matter:** the note is stored with the sign-off in the encrypted audit trail. It is
the evidence an auditor will read.

### 4.5 Users (admin)
**What:** create accounts.

**How:** enter a username and password, pick the role, then **Create account**.

Give each person the *least* role they need.

### 4.6 Zones & documents (admin)
- **Upload SDS:** drop a PDF on the upload area (or click to browse). Chemical name and
  supplier are optional; they are detected from Section 1, and you only need to fill them in if
  detection is wrong.
  - On upload the document is split into its 16 sections, values are extracted, and it is added
    to the indexes.
  - Only real PDFs are accepted.
- **Add chemical:** assign a chemical to a zone. Use the same name as the SDS so retrieval
  finds it; typos are tolerated.
- **New zone:** create a zone (for example `Zone_D`) and optionally list its chemicals.
- **Remove:** the × on a chemical chip removes it from that zone.

*Why it matters:* the zone inventory decides which SDS limits are checked for each reading.

### 4.7 Audit trail (admin)
**What:** every alert creation, sign-off and admin action, newest first. Entries are
append-only and encrypted at rest.

**How:** use the arrows (top right) to page through.

---

## 5. Standard workflows

### A. Bring a new chemical under monitoring
1. Admin uploads its SDS (**Zones & documents → Upload SDS**).
2. Admin adds the chemical to its zone (**Add chemical**).
3. Analyst checks the limits were found (**SDS search**).
4. Watch the zone on **Live environment**. It is now evaluated against the retrieved limits.

### B. Respond to a WARNING
1. A notification appears and the **Sign-off queue** badge increases.
2. Open the alert, read the reading, the limit and the cited source.
3. Optionally generate a safety card in the floor team's language.
4. Take physical action, then the admin approves (or rejects) with a note.
5. Confirm the entry in the **Audit trail**.

### C. Investigate an UNKNOWN zone
1. Click the chemical tiles. "No limit in SDS" means the document has no numeric storage limit.
2. Search the chemical in **SDS search** to confirm.
3. Source a more complete SDS (for example from the manufacturer) and upload it.

---

## 6. Optional: real IoT sensors

The full hardware path is ESP32 + DHT22 → Mosquitto (MQTT over TLS) → bridge → API.

> **Docker on this PC:** Docker Desktop currently fails to start with "initializing Inference
> manager ... The file cannot be accessed by the system". Docker can't create its internal
> sockets. This is a Docker Desktop / Windows problem, not a ChemSentry one. Try restarting
> Windows, updating Docker Desktop, or **Reset to factory defaults** in Docker's error dialog.
> Until then, the in-app simulator exercises the same evaluation path.

1. Generate TLS certificates:
   ```powershell
   python firmware/generate_certs.py --out firmware/certs --devices device1,agent_c_bridge
   ```
2. Start the broker (and PostgreSQL, if you use it):
   ```powershell
   docker compose up -d
   ```
3. Flash the ESP32 (PlatformIO, see `firmware/README.md`). Put Wi-Fi details in
   `firmware/src/secrets.h`, using `secrets.example.h` as the template.
4. Forward MQTT readings into the running API:
   ```powershell
   python -m agents.agent_c_environment.mqtt_http_bridge --api-base http://localhost:8001
   ```
5. With no hardware, publish simulated readings instead:
   ```powershell
   python -m simulator.telemetry_simulator --mode excursion --count 3
   ```

The status bar shows **All systems nominal** only when the database and the MQTT broker are
both reachable. **Degraded** usually just means the broker isn't running, which is fine when
you use the in-app simulator.

---

## 7. Quality checks (run before every commit)

```powershell
black --check .
ruff check .
pytest tests/ -q
cd ui
npm run lint
npm run build
```
Expected: black and ruff clean, **301 passed, 1 skipped**, and the UI builds.

Evaluation (needs the SDS PDFs in `corpus/raw/`):
```powershell
python -m evaluation.run_layer1_eval
python -m evaluation.run_layer5_eval
```
Results are written to `evaluation/results/`.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `WinError 10013` when starting uvicorn | Port already in use | Close the other server or use another `--port` (and update `VITE_API_BASE_URL`) |
| UI shows network errors / cannot sign in | UI pointing at the wrong port | Restart `npm run dev` with `VITE_API_BASE_URL` set to the backend's port |
| Every zone is UNKNOWN | No SDS PDFs loaded, or the SDS has no numeric limit | Add PDFs to `corpus/raw/` or upload them |
| Status bar says Degraded | MQTT broker not running | Expected without Docker; start it with `docker compose up -d` |
| Safety card says "language service unavailable" | No `MISTRAL_API_KEY` | Add the key to `.env` and restart the backend |
| Sent back to sign-in with "session expired" | Token expired (24 h) or backend keys changed | Sign in again |
| New tab asks for sign-in | Sessions are per tab by design | Sign in, or keep using the original tab |
| `Activate.ps1` cannot be loaded | PowerShell execution policy | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` |
