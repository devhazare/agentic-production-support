# Configuration

Configuration is loaded by `core/config/settings.py` using Pydantic settings and
an optional `.env` file. Start from `.env.example` and keep local `.env` files
out of Git.

## Required Local Setup

```bash
cp .env.example .env
```

The default `.env.example` is designed for local mock mode.

## Application Mode

| Variable | Default | Purpose |
|---|---|---|
| `APP_MODE` | `mock` | `mock` uses deterministic local LLM responses. `live` uses the configured provider. |
| `ENVIRONMENT` | `development` | Controls environment metadata and JSON logging in production. |
| `LOG_LEVEL` | `INFO` | Application log level. |

## API

| Variable | Default | Purpose |
|---|---|---|
| `API_HOST` | `0.0.0.0` | API bind host in settings. |
| `API_PORT` | `8000` | API port in settings. |
| `API_V1_PREFIX` | `/api/v1` | Versioned API prefix. |
| `API_REQUEST_TIMEOUT_SEC` | `30` | Request timeout setting. |

The documented startup command is:

```bash
uvicorn api.main:app --reload --port 8000
```

## LLM

| Variable | Default | Status |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | Used only when `APP_MODE=live`. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Implemented. |
| `OLLAMA_MODEL` | `llama3.2` | Implemented. |
| `OPENAI_API_KEY` | empty | Setting exists; provider module is not present in current tree. |
| `OPENAI_MODEL` | `gpt-4o` | Setting exists; provider module is not present in current tree. |
| `ANTHROPIC_API_KEY` | empty | Setting exists; provider module is not present in current tree. |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | Setting exists; provider module is not present in current tree. |
| `LLM_TEMPERATURE` | `0.1` | Used by LLM service calls. |
| `LLM_MAX_TOKENS` | `1000` | Used by LLM service calls. |
| `LLM_TIMEOUT_SEC` | `120` | Used by Ollama HTTP client. |

## Embeddings and RAG

| Variable | Default | Purpose |
|---|---|---|
| `EMBED_MODEL` | `all-MiniLM-L6-v2` | SentenceTransformers model name. |
| `EMBED_DEVICE` | `cpu` | Embedding device. |
| `EMBED_BATCH_SIZE` | `32` | Batch-size setting. |
| `VECTOR_STORE` | `faiss` | Current local vector store. |
| `FAISS_INDEX_PATH` | `./data/faiss_index` | Base path for generated FAISS files. |
| `KNOWLEDGE_BASE_PATH` | `./data/knowledge_base` | Local knowledge documents. |
| `RAG_TOP_K` | `4` | Default retrieval count. |
| `RAG_SIMILARITY_THRESHOLD` | `100.0` | Present in settings; current retrieval returns ranked results. |

Generated FAISS files should not be committed:

- `data/faiss_index.index`
- `data/faiss_index_meta.pkl`
- `data/faiss_index_embedder.pkl`

## Log Sources

Each log source can be set to an exact path or `disabled`.

| Variable | Purpose |
|---|---|
| `MAGENTO_EXCEPTION_LOG_PATH` | Magento exception log. |
| `MAGENTO_SYSTEM_LOG_PATH` | Magento system log. |
| `MAGENTO_ACCESS_LOG_PATH` | Magento access log. |
| `AEM_LOG_PATH` | AEM error log. |
| `JAVA_LOG_PATH` | Java service log. |
| `PYTHON_LOG_PATH` | Python app log. |
| `LOG_POLL_INTERVAL_SEC` | Poll interval for log tailing. |

Magento has additional correlation controls:

- `MAGENTO_FAILURE_THRESHOLD_COUNT`
- `MAGENTO_FAILURE_WINDOW_SECONDS`
- `MAGENTO_INCIDENT_COOLDOWN_SECONDS`

## Persistence

| Variable | Default | Status |
|---|---|---|
| `MONGODB_ENABLED` | `true` | Optional for versioned pipeline result storage. Startup continues if unavailable. |
| `MONGODB_URI` | `mongodb://localhost:27017` | Local default only. |
| `MONGODB_DATABASE` | `agentic_support` | MongoDB database name. |
| `MONGODB_INCIDENTS_COLLECTION` | `incidents` | MongoDB collection name. |
| `LOCAL_STORE_PATH` | `./.local/incident_store.json` | MVP local state store. |
| `LOCAL_AUDIT_PATH` | `./.local/audit_log.jsonl` | MVP local audit log. |

## Optional AWS MVP Settings

The AWS path is disabled by default:

```env
USE_AWS=false
```

When enabled, the code references:

- Bedrock Runtime
- S3
- OpenSearch Serverless
- DynamoDB
- Lambda packaging scripts

These settings are reference-oriented and need cloud-specific review before
production use.

## Alerting and Approval

| Variable | Default | Status |
|---|---|---|
| `SLACK_BOT_TOKEN` | empty | Placeholder only; real delivery is not implemented in the current communication agent. |
| `SLACK_INCIDENTS_CHANNEL` | `#incidents` | Channel metadata. |
| `SLACK_ONCALL_CHANNEL` | `#oncall` | Channel metadata. |
| `JIRA_BASE_URL` | empty | Placeholder only. |
| `JIRA_API_TOKEN` | empty | Placeholder only. |
| `JIRA_PROJECT_KEY` | `SRE` | Used by mock/update payloads. |

## Agent Policy

| Variable | Default | Purpose |
|---|---|---|
| `AUTO_REMEDIATION_ENABLED` | `true` | Present in settings; current action execution remains simulated. |
| `HUMAN_APPROVAL_REQUIRED_SEVERITY` | `["CRITICAL"]` | Present in settings. |
| `CONFIDENCE_REVIEW_THRESHOLD` | `0.75` | MVP confidence threshold for human review. |
| `AUTO_MOCK_CONFIDENCE_THRESHOLD` | `0.85` | MVP threshold for mock remediation. |
| `MAX_PIPELINE_RETRIES` | `3` | Workflow retry setting. |
| `PIPELINE_TIMEOUT_SEC` | `300` | Pipeline timeout setting. |
