# API Reference

The FastAPI application is defined in `api/main.py`.

Interactive documentation is available when the API is running:

```text
http://localhost:8000/api/v1/docs
```

## Start the API

```bash
uvicorn api.main:app --reload --port 8000
```

## System Endpoints

| Method | Path | Status | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/health` | Implemented | Versioned health check with environment, LLM status, vector store, and log sources. |
| `GET` | `/health` | Implemented | MVP health check with AWS mode and region metadata. |

## Versioned Incident Pipeline

Base prefix: `/api/v1`

| Method | Path | Status | Purpose |
|---|---|---|---|
| `POST` | `/incidents/analyze` | Implemented | Runs the async detection -> RCA -> decision -> remediation -> validation -> communication pipeline. |
| `POST` | `/incidents/mock` | Mocked | Triggers a random built-in mock incident. |
| `POST` | `/incidents/{incident_id}/approve` | Implemented | Approves a pending human-approval remediation plan and executes simulated remediation. |
| `POST` | `/incidents/{incident_id}/reject` | Implemented | Rejects a pending human-approval remediation plan. |
| `GET` | `/incidents/history` | Implemented | Returns sample incident history from `data/sample_incidents/incidents.json`. |

### Analyze Payload

```json
{
  "service": "checkout-api",
  "alert_type": "LatencySpike",
  "metrics": {
    "cpu_percent": 72,
    "error_rate": 0.12,
    "latency_p99_ms": 4200
  },
  "logs_snippet": "database connection acquisition timeout",
  "severity": "HIGH",
  "incident_id": "INC-EXAMPLE-001",
  "log_source": "java"
}
```

### Approval Payload

```json
{
  "approved_by": "sre-oncall",
  "comment": "Approved after review"
}
```

## RAG Endpoints

Base prefix: `/api/v1`

| Method | Path | Status | Purpose |
|---|---|---|---|
| `GET` | `/rag/health` | Implemented | Returns FAISS index readiness, loaded chunks, embedder type, and source counts. |
| `POST` | `/rag/search` | Implemented | Searches the local RAG index. |
| `POST` | `/rag/rebuild` | Implemented | Rebuilds the FAISS index from local knowledge files and sample incident history. |

### RAG Search Payload

```json
{
  "query": "checkout API database timeout",
  "top_k": 5
}
```

## Dashboard Telemetry

Base prefix: `/api/v1`

| Method | Path | Status | Purpose |
|---|---|---|---|
| `GET` | `/dashboard/status` | Implemented | Returns incidents, agent activity, RAG status, MongoDB status, MVP states, metrics, and LangGraph metadata. |

The Streamlit dashboard consumes this endpoint.

## AI Ops MVP Endpoints

These endpoints are mounted without the `/api/v1` prefix.

| Method | Path | Status | Purpose |
|---|---|---|---|
| `POST` | `/incidents/trigger` | Implemented | Runs the MVP workflow for an `IncidentEvent`. |
| `GET` | `/incidents/{incident_id}` | Implemented | Reads MVP incident state from local JSON or DynamoDB. |
| `GET` | `/incidents` | Implemented | Lists MVP incident states. |
| `POST` | `/incidents/{incident_id}/approve` | Implemented | Approves an MVP incident and continues simulated remediation. |
| `POST` | `/incidents/{incident_id}/reject` | Implemented | Rejects an MVP incident. |
| `POST` | `/incidents/{incident_id}/needs-more-info` | Implemented | Marks an MVP incident as needing more information. |
| `POST` | `/knowledge/upload` | Implemented | Uploads a runbook/RCA document to local sample data or S3 when AWS is enabled. |
| `POST` | `/knowledge/reindex` | Partial | Indexes documents through the MVP knowledge service; local mode uses keyword search. |

### MVP Incident Payload

```json
{
  "incident_id": "INC-EXAMPLE-001",
  "service_name": "checkout-api",
  "severity": "High",
  "timestamp": "2026-08-03T10:00:00Z",
  "alert_type": "LatencySpike",
  "metric_name": "p99_latency_ms",
  "metric_value": 4200,
  "logs_summary": "database connection acquisition timeout"
}
```

## Notes

- The versioned pipeline and MVP workflow use different models.
- Remediation endpoints execute simulated remediation only.
- Real Slack/Jira delivery is not implemented.
- Authentication and authorization are not implemented in the current API.
