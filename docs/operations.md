# Operations Guide

This guide covers local operation of the current project.

## Local Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

## Run the API

```bash
uvicorn api.main:app --reload --port 8000
```

Health checks:

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/health
```

Interactive API docs:

```text
http://localhost:8000/api/v1/docs
```

## Run the UI

```bash
streamlit run ui/dashboard.py
```

Open:

```text
http://localhost:8501
```

The dashboard reads:

- `GET /api/v1/health`
- `GET /api/v1/dashboard/status`

## Run Mock Mode

Mock mode is the default:

```env
APP_MODE=mock
USE_AWS=false
```

This mode avoids live LLM calls and cloud calls. Remediation remains simulated.

## Run an MVP Sample Incident

With the API running:

```bash
python scripts/simulate_incident.py sample_data/incidents/checkout_latency.json
```

This posts the sample payload to:

```text
POST /incidents/trigger
```

## Run Versioned Incident Analysis

```bash
curl -X POST http://localhost:8000/api/v1/incidents/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "service": "checkout-api",
    "alert_type": "LatencySpike",
    "metrics": {
      "cpu_percent": 72,
      "error_rate": 0.12,
      "latency_p99_ms": 4200
    },
    "logs_snippet": "database connection acquisition timeout",
    "severity": "HIGH",
    "log_source": "java"
  }'
```

## Human Approval

Versioned pipeline approval:

```bash
curl -X POST http://localhost:8000/api/v1/incidents/{incident_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"approved_by":"sre-oncall","comment":"approved after review"}'
```

MVP workflow approval:

```bash
curl -X POST http://localhost:8000/incidents/{incident_id}/approve \
  -H "Content-Type: application/json" \
  -d '{"approver":"sre-oncall","comment":"approved after review"}'
```

Approval continues simulated remediation. It does not perform live
infrastructure changes.

## RAG Operations

Check RAG health:

```bash
curl http://localhost:8000/api/v1/rag/health
```

Rebuild the local FAISS index:

```bash
curl -X POST http://localhost:8000/api/v1/rag/rebuild
```

Search RAG:

```bash
curl -X POST http://localhost:8000/api/v1/rag/search \
  -H "Content-Type: application/json" \
  -d '{"query":"database connection pool timeout","top_k":5}'
```

## Knowledge Upload

The MVP knowledge endpoint stores text locally when `USE_AWS=false`:

```bash
curl -X POST http://localhost:8000/knowledge/upload \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Checkout Timeout Runbook",
    "text": "Steps to investigate checkout timeout incidents.",
    "doc_type": "runbook"
  }'
```

Local upload writes under `sample_data/runbooks` or `sample_data/rca_docs`.

## Log Watchers

The API startup process attempts to start configured log watchers. A watcher is
skipped when its path is set to `disabled` or the file does not exist.

Supported parser families:

- Magento
- AEM
- Java
- Python

Example local setting:

```env
PYTHON_LOG_PATH=./sample_app/logs/app.log
```

## Tests

```bash
pytest tests/ -q
```

The test configuration in `pyproject.toml` enables coverage output.

## Docker

```bash
docker compose up --build
```

The container exposes the API on port `8000`. The Streamlit dashboard is not
included in the current compose service.

## Generated Local Files

These are runtime/generated files and should not be committed:

- `.env`
- `.local/`
- `.coverage`
- `.pytest_cache/`
- `data/faiss_index.index`
- `data/faiss_index_meta.pkl`
- `data/faiss_index_embedder.pkl`
- `sample_app/logs/*.log`
- `sample_logs/**/*.log`
- `terraform.tfstate`
- `infra/terraform/build/`

## Production Caveats

Before production use, add or harden:

- Authentication and authorization.
- Real approval identity and audit controls.
- Real notification delivery.
- Real remediation executors with least-privilege credentials.
- Live verification through monitoring or health checks.
- Secret management outside `.env`.
- CI/CD, dependency scanning, and infrastructure review.
