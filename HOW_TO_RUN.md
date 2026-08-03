# Agentic Support Framework — How to Run

Complete guide covering every flow: setup, API, dashboard, log monitoring, RAG, human approval, and live LLM modes.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [First-Time Setup](#2-first-time-setup)
3. [Starting the System](#3-starting-the-system)
4. [Flow 1 — Manual Incident via API](#4-flow-1--manual-incident-via-api)
5. [Flow 2 — Streamlit Dashboard](#5-flow-2--streamlit-dashboard)
6. [Flow 3 — Automatic Log Monitoring](#6-flow-3--automatic-log-monitoring)
7. [Flow 4 — Human Approval Gate](#7-flow-4--human-approval-gate)
8. [Flow 5 — RAG Knowledge Base](#8-flow-5--rag-knowledge-base)
9. [Flow 6 — Switch to a Real LLM](#9-flow-6--switch-to-a-real-llm)
10. [Agent Pipeline Explained](#10-agent-pipeline-explained)
11. [Decision Matrix](#11-decision-matrix)
12. [API Reference](#12-api-reference)
13. [Configuration Reference](#13-configuration-reference)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.11 | Runtime (`.python-version` enforces this) |
| pip / venv | any | Dependency isolation |
| Ollama *(optional)* | latest | Local LLM — only needed for `APP_MODE=live` |
| MongoDB *(optional)* | 6+ | Incident persistence — can be disabled |

> **Minimum to run:** Python 3.11 only. Everything else is optional for `mock` mode.

---

## 2. First-Time Setup

```bash
# Clone / open the project directory
cd agentic-framework-v4-final

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows

# Install all dependencies
pip install -r requirements.txt

# Copy the environment file
cp .env.example .env
```

The `.env` file ships with sensible defaults — `APP_MODE=mock` and `EMBED_MODEL=tfidf` — so the system runs fully offline with no external services.

---

## 3. Starting the System

Two processes are needed: the **API** and the **UI**.

### Terminal 1 — Start the API

```bash
source .venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

What happens on startup:
- FAISS vector index is loaded (or built from `data/knowledge_base/`)
- Log watchers start tailing any configured log files
- The EventBus wires log anomalies → orchestrator

Verify the API is up:
```bash
curl http://localhost:8000/api/v1/health
# Expected: {"status":"ok","llm_status":"mock", ...}
```

Interactive API docs: `http://localhost:8000/api/v1/docs`

### Terminal 2 — Start the Streamlit Dashboard

```bash
source .venv/bin/activate
streamlit run ui/dashboard.py
```

Dashboard opens at: `http://localhost:8501`

The sidebar will show **"API online"** when the API is reachable.

---

## 4. Flow 1 — Manual Incident via API

Send an alert payload and the full 6-agent pipeline runs synchronously, returning the complete result.

### POST /api/v1/incidents/analyze

```bash
curl -X POST http://localhost:8000/api/v1/incidents/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "service": "magento-checkout",
    "alert_type": "LogAnomaly",
    "log_source": "magento",
    "metrics": {
      "error_rate": 0.8,
      "latency_p99_ms": 2600
    },
    "logs_snippet": "main.CRITICAL: SQLSTATE[HY000]: Lock wait timeout exceeded; try restarting transaction"
  }'
```

**What the payload fields mean:**

| Field | Required | Description |
|---|---|---|
| `service` | Yes | Name of the affected service |
| `alert_type` | Yes | e.g. `LogAnomaly`, `CPUUtilization`, `ServiceDown`, `DatabaseConnections` |
| `metrics` | No | Dict of floats: `cpu_percent`, `error_rate`, `latency_p99_ms`, `db_connections` |
| `logs_snippet` | No | Raw log lines (up to 2000 chars) |
| `severity` | No | Override auto-scoring: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `log_source` | No | `magento`, `aem`, `java`, `python` |

**Example response:**

```json
{
  "incident_id": "INC-A1B2C3D4",
  "service": "magento-checkout",
  "severity": "HIGH",
  "status": "RESOLVED",
  "decision": "AUTO_REMEDIATE",
  "risk_score": 0.75,
  "rca_summary": "Root Cause: CUDA OOM caused by batch_size=128...",
  "remediation_steps": 5,
  "estimated_mttr_minutes": 13,
  "human_approval_needed": false,
  "validation_status": "VALIDATED",
  "validation_passed": true,
  "communication_channels": ["slack:incidents", "jira:incident"],
  "pipeline_duration_ms": 412
}
```

### Other useful example payloads

**Java OOM / memory:**
```json
{
  "service": "user-service",
  "alert_type": "MemoryUtilization",
  "log_source": "java",
  "metrics": {"memory_mb": 3900.0, "error_rate": 0.18},
  "logs_snippet": "java.lang.OutOfMemoryError: GC overhead limit exceeded"
}
```

**DB connection pool exhausted:**
```json
{
  "service": "order-service",
  "alert_type": "DatabaseConnections",
  "log_source": "java",
  "metrics": {"db_connections": 198, "db_max_connections": 200, "error_rate": 0.45},
  "logs_snippet": "HikariPool-1 Connection not available, timed out after 30000ms"
}
```

**Critical service down (forces HUMAN_APPROVAL):**
```json
{
  "service": "payment-service",
  "alert_type": "ServiceDown",
  "metrics": {"cpu_percent": 0, "error_rate": 1.0},
  "logs_snippet": "FATAL: Service is not responding to health checks"
}
```

---

## 5. Flow 2 — Streamlit Dashboard

Open `http://localhost:8501` after starting both processes.

### Tabs explained

| Tab | What it shows |
|---|---|
| **Overview** | Key metrics, live agent pipeline status, incident table, human approval queue |
| **App logs** | Tail any configured log file with level filtering |
| **Anomalies** | All log anomalies detected in the current API process |
| **Agents** | Current state of each agent + LLM token usage |
| **Agent activity** | Timeline of all agent runs with durations |
| **RAG history** | Vector index status, knowledge base search, rebuild button |
| **KPI feeds** | Decision/severity distributions, service incident counts |

### Running a smoke test from the dashboard

1. Open the **Overview** tab
2. Find the **"Run Pipeline Smoke Test"** section at the bottom
3. Click **"Run sample"** — sends a pre-built Magento checkout incident
4. The full JSON result appears inline

### Auto-refresh

The dashboard auto-refreshes every 5 seconds by default. Adjust the slider in the sidebar or toggle it off.

---

## 6. Flow 3 — Automatic Log Monitoring

The API starts log watchers on startup. When enough matching log lines appear within a time window, the watcher fires an anomaly event and the orchestrator runs automatically — no human action needed.

### Step 1 — Enable log paths in `.env`

```ini
# Monitor the sample Python app log
PYTHON_LOG_PATH=./sample_app/logs/app.log

# Monitor Magento logs (correlated across 3 files)
MAGENTO_EXCEPTION_LOG_PATH=./sample_logs/magento/exception.log
MAGENTO_SYSTEM_LOG_PATH=./sample_logs/magento/system.log
MAGENTO_ACCESS_LOG_PATH=./sample_logs/magento/access.log

# How many failures in how many seconds before firing
MAGENTO_FAILURE_THRESHOLD_COUNT=5
MAGENTO_FAILURE_WINDOW_SECONDS=300

# Cooldown between repeated incidents from the same source
MAGENTO_INCIDENT_COOLDOWN_SECONDS=60
```

Set a path to `disabled` to skip that source.

### Step 2 — Restart the API

```bash
# Ctrl+C the running uvicorn, then:
uvicorn api.main:app --reload --port 8000
```

### Step 3 — Generate sample Magento log traffic

```bash
# One-shot: 200 events, 50% failure rate
FAIL_PERCENT=50 ./scripts/generate_magento_logs.sh 200

# Continuous streaming — keeps appending every 2 seconds (run in background)
LOOP=true TRUNCATE=false FAIL_PERCENT=50 SLEEP_SEC=2 \
  ./scripts/generate_magento_logs.sh 20 ./sample_logs/magento &

# Stop streaming
kill %1
```

### Step 4 — Trigger the sample Python app to write errors

```bash
source .venv/bin/activate
python sample_app/trigger_error.py
```

### What happens automatically

```
Log file gets new ERROR/CRITICAL lines
        ↓
LogWatcher detects pattern match, increments window counter
        ↓
Counter crosses threshold → LogAnomalyDetectedEvent published on EventBus
        ↓
api/main.py handler creates AlertPayloadSchema and calls orchestrator.run()
        ↓
Full 6-agent pipeline runs → result saved to MongoDB (if enabled)
        ↓
Incident appears in dashboard Overview tab
```

### Built-in anomaly detection rules

| Rule | Pattern | Threshold |
|---|---|---|
| OOM / heap exhaustion | `OutOfMemoryError`, `Java heap space`, `GC overhead` | 5 hits / 5 min |
| DB connection exhaustion | `Connection is not available`, `pool.*timeout` | 5 hits / 5 min |
| Magento DB deadlock | `SQLSTATE.*Lock wait timeout` | 10 hits / 10 min |
| Circuit breaker open | `Circuit OPEN`, `failing fast` | 3 hits / 2 min |
| CUDA OOM | `torch.cuda.OutOfMemoryError` | 3 hits / 10 min |
| PHP memory limit | `Memory limit reached` | 3 hits / 5 min |
| AEM workflow failure | `WorkflowException.*Step failed` | 3 hits / 5 min |
| Error rate spike | Any `ERROR`/`FATAL`/`CRITICAL` line | 20 hits / 5 min |

---

## 7. Flow 4 — Human Approval Gate

When the Decision Agent outputs `HUMAN_APPROVAL` (CRITICAL severity, or HIGH severity with low RCA confidence), the remediation plan is generated but **not executed**. A human must review and approve.

### When it triggers

See the [Decision Matrix](#11-decision-matrix) below. Any `CRITICAL` incident always requires approval.

Force it with:
```bash
curl -X POST http://localhost:8000/api/v1/incidents/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "service": "payment-gateway",
    "alert_type": "ServiceDown",
    "severity": "CRITICAL",
    "logs_snippet": "FATAL: Payment service unresponsive"
  }'
```

Response will have `"human_approval_needed": true`.

### Approve via dashboard

1. Open `http://localhost:8501` → **Overview** tab
2. Scroll down to the **Human Approval Queue**
3. Enter approver name and comment
4. Click **"Approve and execute"** — the remediation plan runs immediately
5. Or click **"Reject"** to close without executing

### Approve via API

```bash
# Approve
curl -X POST http://localhost:8000/api/v1/incidents/{incident_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"approved_by": "john.smith", "comment": "Reviewed, safe to proceed"}'

# Reject
curl -X POST http://localhost:8000/api/v1/incidents/{incident_id}/reject \
  -H "Content-Type: application/json" \
  -d '{"approved_by": "john.smith", "comment": "Not approved - needs more investigation"}'
```

### List incidents pending approval

```bash
curl http://localhost:8000/api/v1/incidents?status=ESCALATED
```

---

## 8. Flow 5 — RAG Knowledge Base

The RCA and Remediation agents retrieve similar past incidents and runbooks from a FAISS vector index before calling the LLM.

### What is indexed

- `data/knowledge_base/runbook_cuda_oom.md` — CUDA OOM runbook
- `data/knowledge_base/runbook_db_connections.md` — DB connection pool runbook
- `data/knowledge_base/runbook_kafka_lag.md` — Kafka lag runbook
- `data/knowledge_base/fixed_issues.md` — Historical fixed incidents
- `data/knowledge_base/issues.psv` — Pipe-delimited issue history

### Check RAG index health

```bash
curl http://localhost:8000/api/v1/rag/health
```

### Search the knowledge base

```bash
curl -X POST http://localhost:8000/api/v1/rag/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Magento checkout SQLSTATE lock wait timeout", "top_k": 5}'
```

### Seed with historical Magento incidents

```bash
# Generate 500 past incidents into knowledge_base/fixed_issues.md
python scripts/generate_dummy_magento_issues.py --count 500

# Rebuild the FAISS index to pick up new files
curl -X POST http://localhost:8000/api/v1/rag/rebuild
```

Or click **"Rebuild Vector Index"** in the RAG history tab.

### Add a single real resolved incident

```bash
./scripts/add_rag_issue.sh \
  --issueid MAG-001 \
  --type magento \
  --bugis checkout_timeout \
  --descpt "Checkout failed for card payments during peak hours" \
  --priority P1 \
  --seviorty HIGH \
  --start_datetime "2026-05-11 10:00:00" \
  --enddatatime "2026-05-11 10:25:00" \
  --rca "Payment gateway timeout exceeded Magento client timeout during peak" \
  --fixedby "Increased gateway timeout from 10s to 30s, added retry with backoff"

# Then rebuild the index
curl -X POST http://localhost:8000/api/v1/rag/rebuild
```

Or run `./scripts/add_rag_issue.sh` with no arguments for interactive prompts.

---

## 9. Flow 6 — Switch to a Real LLM

### Option A — Ollama (local, free)

```bash
# Install Ollama from https://ollama.com, then:
ollama pull llama3.2
ollama serve          # keep running in a separate terminal
```

Update `.env`:
```ini
APP_MODE=live
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

### Option B — Anthropic Claude

Update `.env`:
```ini
APP_MODE=live
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
```

### Option C — OpenAI

Update `.env`:
```ini
APP_MODE=live
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

After changing `.env`, restart the API:
```bash
# Ctrl+C, then:
uvicorn api.main:app --reload --port 8000
```

Verify LLM is live:
```bash
curl http://localhost:8000/api/v1/health
# "llm_status" will show "online" instead of "mock"
```

> **Fallback behaviour:** If Ollama is unreachable when `APP_MODE=live`, `LLMService` automatically falls back to `MockProvider` without crashing. Watch the API logs for `llm.generate.connection_error`.

---

## 10. Agent Pipeline Explained

Every incident — whether from the API or a log anomaly — flows through this chain:

```
AlertPayloadSchema (input)
        │
        ▼
① IncidentDetectionAgent
   - Parses metrics dict into typed Metrics value object
   - Scores severity: CPU / error_rate / latency / DB utilisation → points
   - Creates Incident entity with incident_id, severity, status=OPEN
   - Publishes IncidentDetectedEvent on EventBus
        │
        ▼
② RCAAgent
   - Queries FAISS index with: "{alert_type} {service} {log snippet}"
   - Retrieves top-4 context chunks (runbooks + past incidents)
   - Builds structured prompt + calls LLM
   - Extracts confidence: HIGH / MEDIUM / LOW from LLM response
   - Returns RCAResult with full analysis text
        │
        ▼
③ DecisionAgent
   - Looks up (Severity × Confidence) in decision matrix
   - Returns: AUTO_REMEDIATE / HUMAN_APPROVAL / MONITOR_ONLY
   - Assigns risk_score: CRITICAL=1.0, HIGH=0.75, MEDIUM=0.5, LOW=0.2
        │
        ▼
④ RemediationAgent
   - Retrieves runbook context from FAISS for remediation
   - Generates 3–6 step plan via LLM (prefixed [SCALE]/[RESTART]/etc.)
   - Parses ESTIMATED_MTTR from LLM response
   - If AUTO_REMEDIATE: executes each step via SimulatedExecutor
   - If HUMAN_APPROVAL: steps created but marked SKIPPED
        │
        ▼
⑤ ValidationAgent
   - Checks RCA confidence is present
   - If AUTO_REMEDIATE: checks plan.executed = True, no FAILED steps
   - If HUMAN_APPROVAL: records "held for approval" as passing check
   - Returns VALIDATED or VALIDATION_FAILED
        │
        ▼
⑥ CommunicationAgent
   - Builds notification subject + message
   - Selects channels: slack:incidents / slack:oncall / jira / email
   - Assembles full report dict (persisted in PipelineResult)
   - Delivery is prepared but not sent (connectors plugged in separately)
        │
        ▼
PipelineResult (returned to API caller / saved to MongoDB)
```

---

## 11. Decision Matrix

The Decision Agent uses this table. It cannot be overridden by the API payload.

| Severity | RCA Confidence | Decision |
|---|---|---|
| CRITICAL | HIGH | HUMAN_APPROVAL |
| CRITICAL | MEDIUM | HUMAN_APPROVAL |
| CRITICAL | LOW | HUMAN_APPROVAL |
| HIGH | HIGH | AUTO_REMEDIATE |
| HIGH | MEDIUM | HUMAN_APPROVAL |
| HIGH | LOW | HUMAN_APPROVAL |
| MEDIUM | HIGH | AUTO_REMEDIATE |
| MEDIUM | MEDIUM | AUTO_REMEDIATE |
| MEDIUM | LOW | MONITOR_ONLY |
| LOW | HIGH | MONITOR_ONLY |
| LOW | MEDIUM | MONITOR_ONLY |
| LOW | LOW | MONITOR_ONLY |

> In mock mode the LLM always returns `HIGH` confidence, so a `HIGH` severity incident will always `AUTO_REMEDIATE`. A `CRITICAL` severity always triggers `HUMAN_APPROVAL` regardless of confidence.

---

## 12. API Reference

Base URL: `http://localhost:8000/api/v1`

| Method | Path | Description |
|---|---|---|
| GET | `/health` | System health: LLM status, vector store, log sources |
| POST | `/incidents/analyze` | Run full pipeline on an alert payload |
| GET | `/incidents` | List all incidents (optional `?status=OPEN`) |
| GET | `/incidents/{id}` | Get single incident by ID |
| POST | `/incidents/{id}/approve` | Approve and execute a pending remediation |
| POST | `/incidents/{id}/reject` | Reject a pending remediation |
| GET | `/rag/health` | RAG index status and chunk count |
| POST | `/rag/search` | Search knowledge base with a query string |
| POST | `/rag/rebuild` | Rebuild FAISS index from knowledge base files |
| GET | `/dashboard/status` | Full dashboard data (metrics, agents, anomalies, incidents) |

Full interactive docs: `http://localhost:8000/api/v1/docs`

Postman collection: `postman_collection.json` — import directly into Postman.

---

## 13. Configuration Reference

All settings live in `.env`. Key options:

```ini
# ── App mode ──────────────────────────────────────────────────────────
APP_MODE=mock            # mock | live
ENVIRONMENT=development  # development | staging | production
LOG_LEVEL=INFO

# ── LLM (only when APP_MODE=live) ─────────────────────────────────────
LLM_PROVIDER=ollama      # ollama | openai | anthropic
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-6
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o

# ── Embeddings ─────────────────────────────────────────────────────────
EMBED_MODEL=tfidf        # tfidf (fast, no download) | all-MiniLM-L6-v2 (semantic)

# ── Log sources ────────────────────────────────────────────────────────
PYTHON_LOG_PATH=./sample_app/logs/app.log
MAGENTO_EXCEPTION_LOG_PATH=./sample_logs/magento/exception.log
MAGENTO_SYSTEM_LOG_PATH=./sample_logs/magento/system.log
MAGENTO_ACCESS_LOG_PATH=./sample_logs/magento/access.log
# Set any path to "disabled" to skip that source
AEM_LOG_PATH=disabled
JAVA_LOG_PATH=disabled

# ── Incident thresholds ─────────────────────────────────────────────────
MAGENTO_FAILURE_THRESHOLD_COUNT=5
MAGENTO_FAILURE_WINDOW_SECONDS=300
MAGENTO_INCIDENT_COOLDOWN_SECONDS=60
LOG_POLL_INTERVAL_SEC=5

# ── Persistence ─────────────────────────────────────────────────────────
MONGODB_ENABLED=true
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=agentic_support
MONGODB_INCIDENTS_COLLECTION=incidents

# ── Alerting ────────────────────────────────────────────────────────────
SLACK_BOT_TOKEN=
JIRA_BASE_URL=
JIRA_PROJECT_KEY=SRE
```

---

## 14. Troubleshooting

### API fails to start

```
ImportError: No module named 'fastapi'
```
→ Virtual environment not activated. Run `source .venv/bin/activate` first.

### FAISS index not building

```
app.startup.index_skipped
```
→ Normal on first run if `EMBED_MODEL=all-MiniLM-L6-v2` and the model hasn't downloaded yet. Use `EMBED_MODEL=tfidf` for instant startup.

### Dashboard shows "API offline"

→ API is not running on port 8000. Start it first with `uvicorn api.main:app --reload --port 8000`.

### No incidents appearing from log monitoring

1. Check the log path exists and is not `disabled` in `.env`
2. Restart the API after changing `.env`
3. The threshold must be crossed: default is 5 failures within 300 seconds
4. Lower the threshold for testing: `MAGENTO_FAILURE_THRESHOLD_COUNT=2`

### MongoDB connection errors in logs

→ Expected if MongoDB is not running. Set `MONGODB_ENABLED=false` in `.env` to disable persistence. Incidents will be held in memory only.

### LLM returns empty response in live mode

→ Ollama is not running or the model is not pulled. Run `ollama serve` and `ollama pull llama3.2`. The system will fall back to mock automatically.

### Run tests

```bash
source .venv/bin/activate
pytest tests/ -v
pytest tests/unit/ -v           # unit tests only
pytest tests/integration/ -v    # integration tests only
pytest tests/ -v --cov=.        # with coverage report
```