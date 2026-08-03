# API and Lambda Mapping

The FastAPI app can run locally with Uvicorn and also includes an AWS Lambda
entry point.

## Local API

| Route family | Router | Purpose |
|---|---|---|
| `/api/v1/incidents/*` | `api/v1/routers/incidents.py` | Versioned incident pipeline and approval. |
| `/api/v1/rag/*` | `api/v1/routers/rag.py` | Local FAISS RAG health, search, and rebuild. |
| `/api/v1/dashboard/status` | `api/v1/routers/dashboard.py` | Dashboard telemetry. |
| `/incidents/*` | `api/v1/routers/ops_mvp.py` | AI Ops MVP workflow. |
| `/knowledge/*` | `api/v1/routers/ops_mvp.py` | MVP knowledge upload and reindex. |

## Lambda Entry Points

- `api/aws_lambda.py`
- `api/v1/routers/ops_mvp.py::lambda_handler`

Packaging scripts create zip files under `infra/terraform/build/`, which should
not be committed.

## Notes

The AWS path is experimental and requires cloud, security, and IAM review before
production use.
