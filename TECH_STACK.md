# ChemSentry — Tech Stack & What to Download

Quick reference: what technology each layer uses, and what to install before you start
coding. For folder structure, Git workflow, and hardware procurement, see `setup.md`.

---

## 1. Tech Stack by Layer

| Layer | Technology | Notes |
|---|---|---|
| **Language** | Python 3.11 | Matches every lab (sklearn, nltk, mlxtend) |
| **API Gateway** | FastAPI + Pydantic + Uvicorn | Typed models, async, auto-generated docs |
| **Agent comms** | MCP Python SDK (agent↔agent), MQTT (sensor↔Agent C), HTTPS/REST (client↔gateway) | Brief explicitly requires a named protocol |
| **Crawler** | `requests` + `BeautifulSoup4`, `urllib.robotparser` for `robots.txt` | Lecture 11 |
| **Regex extraction** | Python `re` (standard library) | Lab 07 — primary SDS value extraction |
| **Preprocessing** | `nltk` (tokenizer, stopwords, stemmer/lemmatizer) | Lab 02 |
| **Inverted/positional index** | Hand-built (no library) | Lab 03 — this is the deliverable, not a black box |
| **Tolerant retrieval** | Hand-built k-gram index + `nltk.metrics.distance.edit_distance` | Lab 04 |
| **TF-IDF ranking** | `scikit-learn` (`TfidfVectorizer`, `cosine_similarity`) | Lab 05 |
| **Index elimination** | Hand-built (high-IDF filter + Jaccard filter) | Lab 06A |
| **Rule-based chat fast path** | Plain Python keyword matching | Lab 06B |
| **Severity classification** | `scikit-learn` (`DecisionTreeClassifier`, `train_test_split`, `classification_report`) | Lab 08 |
| **Co-storage discovery** | `mlxtend` (`apriori`, `association_rules`, `TransactionEncoder`) | Lab 09 |
| **LLM** | Mistral API (free tier) | Summarisation, translation, open-query orchestration only — never the safety decision |
| **Firmware** | Arduino C++ via PlatformIO | ESP32 + DHT22 |
| **Sensor → broker** | `PubSubClient` (device side), Eclipse Mosquitto (broker), `paho-mqtt` (Python side) | TLS on port 8883 |
| **Database** | PostgreSQL (or SQLite for local dev) via SQLAlchemy | Inventory, zones, audit log |
| **Auth** | `python-jose` (JWT) + `passlib` (hashing) | RBAC: Operator / Safety Officer / Admin |
| **Frontend** | React + Vite + Tailwind CSS | Three modules: Live Environment, Reconciliation, Supervisor |
| **Charts** | Recharts | Evaluation results, compliance dashboard |
| **Containerisation** | Docker + Docker Compose | One command spins up broker + database |
| **CI** | GitHub Actions | Lint + test + evaluation regression check on every PR |
| **Testing** | `pytest` + `pytest-cov` | Per-component, tied to the lab it demonstrates |
| **Marketing site** | Static HTML or Astro/Next.js + Google Analytics 4 | Lecture 12 |

**Deliberately not used:** vector databases, embedding models, or RAG frameworks as the core retrieval mechanism. This is a classical-IR project by design — see `ChemSentry_Final_Plan.md` for why.

---

## 2. What to Download

### 2.1 Everyone installs this (regardless of your slice)

| Tool | Link |
|---|---|
| Git | https://git-scm.com |
| Python 3.11 | https://www.python.org/downloads/ (or `pyenv` on Mac/Linux) |
| VS Code | https://code.visualstudio.com |
| Docker Desktop | https://www.docker.com/products/docker-desktop |
| Node.js 20 LTS | https://nodejs.org (or via `nvm`) |
| GitHub account | Get added as a collaborator on the repo; enable 2FA |

### 2.2 VS Code extensions (install as a team)

```
Python (Microsoft)
Pylance
Black Formatter
Ruff
ESLint
Prettier
PlatformIO IDE
Docker
Thunder Client
Claude Code
```

### 2.3 Python — run once per machine

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet')"
```

`requirements.txt`:

```text
# API layer
fastapi
uvicorn[standard]
pydantic

# Auth & security
python-jose[cryptography]
passlib[bcrypt]

# Retrieval & NLP
nltk
scikit-learn

# Classification / data handling
pandas

# Association rules
mlxtend

# Crawling
requests
beautifulsoup4

# MQTT
paho-mqtt

# Database
sqlalchemy
psycopg2-binary          # skip if using SQLite locally

# LLM
mistralai

# Testing & quality
pytest
pytest-cov
black
ruff
```

### 2.4 Frontend

```bash
cd ui/
npm create vite@latest . -- --template react
npm install
npm install -D tailwindcss postcss autoprefixer
npm install recharts axios
```

### 2.5 Firmware (Member 4)

- **PlatformIO** — VS Code extension, handles ESP32 board packages automatically
- **USB driver** — CP210x or CH340 depending on your specific ESP32 board; check before ordering hardware

### 2.6 Infrastructure — no manual install, runs via Docker

```yaml
# handled by docker-compose.yml
mosquitto   (eclipse-mosquitto)
postgres    (postgres:16)
```

---

## 3. Per-Member Extras

| Member | Install beyond the baseline |
|---|---|
| M1 (crawler, extraction, indexing) | Nothing extra |
| M2 (retrieval, ranking, evaluation) | Verify `scikit-learn` + `nltk` data downloaded and working before Week 4 |
| M3 (classification, Apriori, LLM) | `mlxtend`; get a Mistral API key issued in Week 3 |
| M4 (IoT, gateway, security, frontend) | PlatformIO, USB driver, Docker confirmed working, MQTT TLS certs generated |

---

## 4. Verify You're Ready

```bash
pytest tests/ -v            # passes, even with stub tests
docker compose ps           # broker + database running
cd ui && npm run dev        # frontend starts locally
git checkout -b test/<name> # can branch and push
```

If all four pass, you're ready for Week 3 work.
