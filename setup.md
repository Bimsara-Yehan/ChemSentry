# ChemSentry — Project Setup Guide

This document covers everything needed **before implementation starts**: repository structure, software to install, hardware to procure, and the team workflow conventions. Every member should complete Section 3 (Environment Setup) regardless of which slice they own — cross-training depends on everyone being able to run the whole system locally.

---

## 1. Repository Structure

```
chemsentry/
├── README.md                      setup · usage · architecture · contributors
├── .env.example                   template for required environment variables
├── .gitignore
├── docker-compose.yml              spins up broker, database, and all services locally
│
├── docs/
│   ├── architecture.md
│   ├── responsible-ai.md
│   ├── evaluation-results.md
│   └── adr/                       architecture decision records — one file per major decision
│
├── corpus/
│   ├── crawler/                   M1 — frontier, robots.txt handling, politeness delay
│   └── raw/                       .gitignored — fetched SDS PDFs live here, not in git
│
├── extraction/                    M1 — Lab 07: regex-based section and value extraction
├── preprocessing/                 M1 — Lab 02: tokenizer, stop words, stemming
├── indexing/                      M1/M2 — Labs 03, 04: inverted, positional, k-gram indexes
│
├── agents/
│   ├── agent_a_retrieval/         M2 — tolerant matching, TF-IDF ranking, elimination
│   ├── agent_b_analysis/          M3 — reconciliation, classifier, Apriori, chat, LLM calls
│   ├── agent_c_environment/       M4 — MQTT subscriber, zone state, excursion detection
│   └── protocols/                 MCP tool schema definitions shared across agents
│
├── safety/                        M2/M3 — deterministic state machine, provenance model
├── firmware/                      M4 — ESP32 sketches (PlatformIO project)
├── simulator/                     M4 — MQTT telemetry simulator for demo/testing
│
├── api/                           M4 — FastAPI gateway, auth, RBAC, request models
│
├── ui/
│   ├── live-environment/          M4 — real-time zone conditions
│   ├── reconciliation/            M4 — document query and conflict view
│   └── supervisor/                M4 — sign-off queue and compliance dashboard
│
├── evaluation/
│   ├── benchmarks/                query sets + hand-assessed relevance judgements
│   └── results/                   generated metrics tables, checked in after each run
│
├── marketing/                     M4 — landing site + GA4 config
│
└── tests/
    ├── test_indexing/
    ├── test_retrieval/
    ├── test_extraction/
    └── test_safety_states/
```

**Convention:** each top-level directory maps to one member's primary slice. This keeps individual contribution visible in the commit history, which the viva checks.

---

## 2. What to Install — Software

### 2.1 Everyone (baseline, install this regardless of your slice)

| Tool | Purpose | Notes |
|---|---|---|
| **Git** | Version control | [git-scm.com](https://git-scm.com) |
| **GitHub account** | Add all 4 members as collaborators on the repo | Enable 2FA — GitHub requires it for some org features |
| **Python 3.11** | Core language for indexing, agents, API | Use `pyenv` (Mac/Linux) or the official installer (Windows) to avoid version conflicts |
| **VS Code** | Shared IDE | [code.visualstudio.com](https://code.visualstudio.com) |
| **Docker Desktop** | Runs Mosquitto, PostgreSQL, and services consistently across everyone's machines | Includes Docker Compose |
| **Node.js 20 LTS + npm** | Frontend build tooling | Use `nvm` to manage versions if you already have other Node projects |

### 2.2 VS Code extensions (install as a team so reviews look consistent)

```
Python (Microsoft)
Pylance
Black Formatter
Ruff
ESLint
Prettier
PlatformIO IDE          — firmware only, but fine to have installed by everyone
Docker
Thunder Client            — or REST Client, for testing FastAPI endpoints
```

### 2.3 Python packages

Create a virtual environment first, then install:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` — grouped by what each package is for:

```text
# API layer
fastapi
uvicorn[standard]
pydantic

# Auth & security
python-jose[cryptography]
passlib[bcrypt]

# Retrieval & NLP (Labs 02–06)
nltk
scikit-learn

# Classification (Lab 08)
pandas

# Association rules (Lab 09)
mlxtend

# Crawling (Lecture 11)
requests
beautifulsoup4

# MQTT (Agent C)
paho-mqtt

# Database
sqlalchemy
psycopg2-binary          # only needed if using PostgreSQL rather than SQLite

# LLM integration
anthropic                 # or openai, depending on which API the team picks

# Testing & quality
pytest
pytest-cov
black
ruff
```

After installing, download the NLTK data used by the preprocessing pipeline:

```python
# Run once — fetches the corpora nltk's tokenizer and stemmer depend on
import nltk
nltk.download("punkt")
nltk.download("stopwords")
nltk.download("wordnet")
```

### 2.4 Frontend packages

```bash
cd ui/
npm create vite@latest . -- --template react
npm install
npm install -D tailwindcss postcss autoprefixer
npm install recharts axios
```

### 2.5 Firmware tooling (Member 4, primarily)

- **PlatformIO** (VS Code extension, installed above) — handles ESP32 board packages and library dependencies automatically, no separate Arduino IDE install needed
- **CP210x or CH340 USB driver** — needed on Windows/Mac to talk to most ESP32 dev boards over USB; check which chip your specific board uses before ordering

### 2.6 Infrastructure (runs via Docker, nothing to install directly)

| Service | Image |
|---|---|
| MQTT broker | `eclipse-mosquitto` |
| Database | `postgres:16` (or skip this and use SQLite for local dev) |

These are defined in `docker-compose.yml` — running `docker compose up` brings up both with no manual install.

---

## 3. Environment Setup — Step by Step

Run through this once, individually, before Week 3 work begins.

```bash
# 1. Clone the repo
git clone https://github.com/<org>/chemsentry.git
cd chemsentry

# 2. Python environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet')"

# 3. Frontend environment
cd ui && npm install && cd ..

# 4. Copy the environment template and fill in local values
cp .env.example .env

# 5. Bring up infrastructure (broker + database)
docker compose up -d

# 6. Verify everything is reachable
pytest tests/ -v
```

### 3.1 `.env.example` — copy this to `.env` and fill in real values

```text
# Database
DATABASE_URL=postgresql://chemsentry:localdev@localhost:5432/chemsentry

# MQTT broker
MQTT_HOST=localhost
MQTT_PORT=8883
MQTT_TLS_CERT_PATH=./firmware/certs/device.crt

# Auth
JWT_SECRET_KEY=replace-with-a-random-string-per-environment
JWT_ALGORITHM=HS256

# LLM
ANTHROPIC_API_KEY=your-key-here

# Marketing site
GA4_MEASUREMENT_ID=G-XXXXXXX
```

**Never commit `.env`.** It's already in `.gitignore` — double-check before your first commit that it stays that way.

### 3.2 You're ready when…

- [ ] `pytest tests/` runs and passes (even with mostly empty test stubs at this stage)
- [ ] `docker compose ps` shows the broker and database containers running
- [ ] `npm run dev` inside `ui/` starts the frontend on localhost
- [ ] You can `git checkout -b test/<yourname>` and push a branch without permission errors

---

## 4. Hardware to Procure (Member 4, order in Week 3)

| Item | Qty | Approx. cost (LKR) | Notes |
|---|---|---|---|
| ESP32 DevKit | 2–3 | 2,500 each | Confirm USB driver (CP210x vs CH340) before ordering |
| DHT22 sensor | 2 | 600 each | Temperature + humidity |
| Breadboard + jumper wires | 1 set | ~1,000 | |
| USB cables (data-capable, not charge-only) | 2–3 | ~300 each | Easy to overlook — some cables are power-only |
| Power supply / USB hub | 1 | ~1,500 | If running nodes away from a laptop |

Optional, add later as an extension:

| Item | Qty | Approx. cost (LKR) |
|---|---|---|
| MQ-135 gas sensor | 1 | 900 |
| RC522 RFID reader + tags | 1 set | 2,500 |

Order Week 3 — shipping delays are a real risk to the Week 5 "sensors publishing" milestone.

---

## 5. Git Workflow

**Branching:**
```
main                    — always deployable, protected branch
feature/<slice>-<desc>  — e.g. feature/retrieval-tfidf-ranking
fix/<desc>
```

**Commits:** short imperative subject line, e.g. `Add k-gram index builder for chemical name resolution`. Avoid `fix stuff` / `wip` on anything merging into `main`.

**Pull requests:**
- One reviewer minimum before merge — per the cross-training plan, review someone else's slice, not just your own
- CI (lint + tests) must pass before merge
- Link the PR to the relevant week/milestone in the project board

**Branch protection on `main`** (set this up in GitHub repo settings in Week 3):
- Require PR review before merge
- Require status checks (CI) to pass

---

## 6. Per-Member Checklist

| Member | Beyond the baseline, also install/set up |
|---|---|
| **M1** (crawler, extraction, indexing) | Nothing extra — baseline covers it |
| **M2** (retrieval, ranking, evaluation) | `scikit-learn`, `nltk` data downloaded and verified working — test with a throwaway script before Week 4 |
| **M3** (classification, Apriori, LLM) | `mlxtend`, an Anthropic or OpenAI API key (get this issued in Week 3, not Week 8) |
| **M4** (IoT, gateway, security, frontend, deployment) | PlatformIO, USB driver for the ESP32 board, Docker Desktop confirmed working, Mosquitto TLS certs generated |

---

## 7. Common Setup Issues

| Problem | Likely fix |
|---|---|
| `pip install` fails on `psycopg2-binary` | Use SQLite locally instead — swap `DATABASE_URL` to a `sqlite:///` path, skip Postgres for solo dev |
| ESP32 not detected over USB | Wrong driver installed — check whether your board uses CP210x or CH340 and install the matching one |
| `nltk` errors about missing corpora | Re-run the `nltk.download(...)` step — it's a common miss after a fresh clone |
| Docker containers won't start | Check port conflicts — something else on your machine may already be using 5432 or 8883 |
| Frontend `npm install` errors | Confirm Node 20 LTS — older versions sometimes fail on newer Vite/React |

---

## 8. First Week 3 Meeting Agenda

Once everyone has completed Section 3:

1. Confirm domain registration (Chemical Engineering) is submitted
2. Walk through the repo structure together — make sure everyone can find their slice
3. Assign the four roles if not already settled
4. Order hardware (Section 4)
5. Agree the benchmark query set owner and deadline (should exist by end of Week 3)
6. Set GitHub branch protection rules
7. Confirm everyone can run `pytest`, `docker compose up`, and `npm run dev` locally
