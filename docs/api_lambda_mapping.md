# API to Lambda Mapping

This document maps the current API routes to the AWS Lambda service that handles them.

## AWS API Gateway

Base URL:

```text
https://t1fdcvm0zj.execute-api.ap-south-1.amazonaws.com
```

API Gateway type: HTTP API

Region:

```text
ap-south-1
```

## Public AWS Routes

| Method | Route | Lambda | Handler | Purpose |
|---|---|---|---|---|
| `GET` | `/health` | `ai-ops-mvp-dev-api` | `api.aws_lambda.handler` | MVP health check |
| `POST` | `/incidents/trigger` | `ai-ops-mvp-dev-api` | `api.aws_lambda.handler` | Trigger MVP incident workflow |
| `GET` | `/incidents` | `ai-ops-mvp-dev-api` | `api.aws_lambda.handler` | List MVP incidents |
| `GET` | `/incidents/{incident_id}` | `ai-ops-mvp-dev-api` | `api.aws_lambda.handler` | Get one MVP incident |
| `POST` | `/incidents/{incident_id}/approve` | `ai-ops-mvp-dev-api` | `api.aws_lambda.handler` | Approve MVP remediation |
| `POST` | `/incidents/{incident_id}/reject` | `ai-ops-mvp-dev-api` | `api.aws_lambda.handler` | Reject MVP remediation |
| `POST` | `/incidents/{incident_id}/needs-more-info` | `ai-ops-mvp-dev-api` | `api.aws_lambda.handler` | Mark incident as needing more info |
| `POST` | `/knowledge/upload` | `ai-ops-mvp-dev-api` | `api.aws_lambda.handler` | Upload runbook/RCA knowledge |
| `POST` | `/knowledge/reindex` | `ai-ops-mvp-dev-api` | `api.aws_lambda.handler` | Reindex knowledge |
| `POST` | `/magento/logs/generate` | `ai-ops-mvp-dev-magento-logs-generator` | `services.magento_log_generator_lambda.handler` | Generate Magento sample log incidents |

## API Gateway Routing

| API Gateway Route | Integration Target |
|---|---|
| `POST /magento/logs/generate` | `ai-ops-mvp-dev-magento-logs-generator` |
| `ANY /` | `ai-ops-mvp-dev-api` |
| `ANY /{proxy+}` | `ai-ops-mvp-dev-api` |

The exact route `POST /magento/logs/generate` takes precedence over the greedy proxy route, so Magento log generation is handled by the dedicated Lambda.

## Non-API Lambda

| Trigger | Lambda | Handler | Purpose |
|---|---|---|---|
| EventBridge rule `ai-ops-mvp-dev-incident-trigger` | `ai-ops-mvp-dev-incident-ingestion` | `api.v1.routers.ops_mvp.lambda_handler` | Ingest CloudWatch/EventBridge-style incidents |
| Lambda invoke from workflow | `ai-ops-mvp-dev-mock-remediation` | `services.remediation_lambda.handler` | Mock dry-run remediation |

## Local-Only Full FastAPI Routes

These are available when running local FastAPI with:

```bash
EMBED_MODEL=tfidf uvicorn api.main:app --reload --port 8000
```

Local base URL:

```text
http://localhost:8000/api/v1
```

| Method | Route | Served By | Notes |
|---|---|---|---|
| `GET` | `/api/v1/health` | local `api.main:app` | Full app health |
| `GET` | `/api/v1/dashboard/status` | local `api.main:app` | Streamlit dashboard data |
| `POST` | `/api/v1/incidents/analyze` | local `api.main:app` | Full agent pipeline |
| `POST` | `/api/v1/incidents/mock` | local `api.main:app` | Random mock incident |
| `POST` | `/api/v1/incidents/{incident_id}/approve` | local `api.main:app` | Full pipeline approval |
| `POST` | `/api/v1/incidents/{incident_id}/reject` | local `api.main:app` | Full pipeline rejection |
| `GET` | `/api/v1/incidents/history` | local `api.main:app` | Sample incident history |
| `GET` | `/api/v1/rag/health` | local `api.main:app` | RAG health |
| `POST` | `/api/v1/rag/search` | local `api.main:app` | RAG search |
| `POST` | `/api/v1/rag/rebuild` | local `api.main:app` | Rebuild FAISS index |

The deployed AWS API Lambda currently uses `api/aws_lambda.py`, which includes only the MVP root router. The full `/api/v1` dashboard/RAG/full-pipeline routes are local unless the Lambda adapter is changed to serve `api.main:app`.

## Deployment Notes

Package the existing MVP API Lambda:

```bash
./scripts/package_lambda.sh
```

Package only the dedicated Magento log generator Lambda:

```bash
./scripts/package_magento_logs_lambda.sh
```

Apply with the existing stack variables:

```bash
terraform -chdir=infra/terraform apply \
  -var='aws_region=ap-south-1' \
  -var='budget_alert_email=dev.hazare@gmail.com' \
  -var='monthly_budget_limit_usd=30' \
  -var='enable_deletion_protection=false'
```
