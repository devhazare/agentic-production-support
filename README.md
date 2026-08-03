# Agentic Support Framework

AI operations MVP for incident detection, root-cause analysis, decisioning, and
mock remediation. It combines FastAPI, LangGraph, local RAG with FAISS, log
watchers, a Streamlit dashboard, and optional AWS reference integrations.

The default setup runs locally in mock mode without cloud credentials or a live
LLM. Remediation is designed as a safe demo flow unless you explicitly wire real
execution backends.

## What It Does

- Accepts incident alerts through a FastAPI API.
- Parses and correlates Magento, AEM, Java, and Python logs.
- Runs a multi-agent workflow for detection, RCA, decisioning, remediation,
  validation, and communication.
- Retrieves runbook and incident context from a local FAISS-backed knowledge
  base.
- Exposes a Streamlit dashboard for incidents, anomalies, agent activity, and
  RAG history.
- Includes optional AWS/Bedrock/OpenSearch/S3/DynamoDB/Terraform reference
  components for production-style architecture exploration.

## Quick Start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Start the API:

```bash
uvicorn api.main:app --reload --port 8000
```

Open:

- API health: http://localhost:8000/api/v1/health
- API docs: http://localhost:8000/api/v1/docs

Start the dashboard in a second terminal:

```bash
streamlit run ui/dashboard.py
```

Open: http://localhost:8501

## Demo Incident

With the API running:

```bash
python scripts/simulate_incident.py sample_data/incidents/checkout_latency.json
```

You can also use the sample payloads in `HOW_TO_RUN.md` or the included
Postman collection.

## Safety Notes

- `.env.example` defaults to local/mock-friendly settings.
- `USE_AWS=false` keeps AWS integrations disabled.
- Local incident and audit state is written under `.local/`, which is ignored by
  Git.
- Generated FAISS index files are ignored and can be rebuilt from the curated
  knowledge base.

## Documentation

- Full runbook: [HOW_TO_RUN.md](HOW_TO_RUN.md)
- Architecture: [docs/architecture.md](docs/architecture.md)
- Deployment notes: [docs/deployment.md](docs/deployment.md)
- AWS production readiness: [docs/aws_production_readiness.md](docs/aws_production_readiness.md)
- Open-source readiness notes: [OPEN_SOURCE_READINESS_REPORT.md](OPEN_SOURCE_READINESS_REPORT.md)

## Architecture Patterns

---

### Design Patterns Applied

| Pattern | Where used |
|---|---|
| **Template Method** | `BaseAgent.run()` — skeleton algorithm, subclasses override `_execute()` |
| **Strategy** | `LLMProviderProtocol`, `SeverityScorer`, `ActionExecutor`, `LogParser` |
| **Factory** | `LLMFactory`, `LogParserFactory`, `OrchestratorBuilder` |
| **Builder** | `OrchestratorBuilder` — wires full DI graph |
| **Observer / Pub-Sub** | `EventBus` — agents publish domain events, never call each other directly |
| **Chain of Responsibility** | `Orchestrator` — routes payload through detection → RCA → decision → remediation |
| **Command** | `RemediationStep` — each step is an executable command |
| **Repository** | `FAISSIndexer` / `RAGRetriever` — abstracts vector storage |
| **Composite** | `MultiSourceWatcher` — aggregates multiple log watchers |
| **Facade** | `Orchestrator` hides agent wiring from API layer |
| **Singleton** | `get_settings()`, `get_event_bus()` — module-level cached instances |
| **Context Object** | `AgentContext` — carries cross-cutting state through pipeline |
| **Value Object** | `Metrics`, `LogLine`, `ContextChunk` — immutable, no identity |
| **Entity** | `Incident` — has identity (`incident_id`), mutable lifecycle |

---

### Python Standards

- **Type hints** on all public functions and class attributes
- **`from __future__ import annotations`** in every module (PEP 563)
- **Pydantic v2** for all external data (API schemas, settings)
- **Dataclasses** for internal domain objects
- **Abstract base classes** (`abc.ABC`) for all interfaces
- **`match` statement** (Python 3.10+) in `LLMFactory`
- **`structlog`** for structured, context-aware logging (never `print()`)
- **`pytest-asyncio`** for async agent tests
- **Exception hierarchy** — never raise bare `Exception`

---

### Project Structure

```
agentic-framework/
├── agents/
│   ├── base/           Template Method base agent
│   ├── detection/      IncidentDetectionAgent
│   ├── rca/            RCAAgent (RAG + LLM)
│   ├── decision/       DecisionAgent (severity matrix)
│   └── remediation/    RemediationAgent (Command pattern)
├── orchestration/      Orchestrator + Builder
├── rag/
│   ├── indexer/        FAISSIndexer (Repository)
│   └── retriever/      RAGRetriever
├── log_monitors/
│   ├── parsers/        LogParser strategies (Magento/AEM/Java/Python)
│   └── watchers/       LogWatcher + MultiSourceWatcher (Observer)
├── services/
│   └── llm/            LLMFactory + provider strategies
├── core/
│   ├── config/         Pydantic Settings (Singleton)
│   ├── events/         EventBus (Pub-Sub)
│   ├── exceptions/     Domain exception hierarchy
│   └── logging/        structlog setup
├── models/             Domain entities + Pydantic API schemas
├── api/
│   └── v1/routers/     FastAPI routers (OpenAPI-documented)
└── tests/
    ├── unit/           Agent + parser unit tests (mocked deps)
    └── integration/    End-to-end pipeline tests
```

## AI operational intelligence MVP

This repo now includes the CloudWatch/EventBridge-style incident workflow in the existing FastAPI app:

- `POST /incidents/trigger`
- `GET /incidents/{incident_id}`
- `POST /incidents/{incident_id}/approve`
- `POST /incidents/{incident_id}/reject`
- `GET /incidents`
- `GET /health`
- `POST /knowledge/upload`
- `POST /knowledge/reindex`

The MVP uses LangGraph for orchestration in `orchestration/langgraph_workflow.py`, Bedrock/OpenSearch/S3/DynamoDB wrappers under `services/`, and mock Slack/Jira/remediation integrations. Local mode is the default and stores incident history in `.local/`.

Demo:

```bash
uvicorn api.main:app --reload --port 8000
python scripts/simulate_incident.py sample_data/incidents/checkout_latency.json
```

AWS deployment baseline:

```bash
./scripts/package_lambda.sh
cd infra/terraform
terraform init
terraform plan
terraform apply
```

See [docs/deployment.md](docs/deployment.md) and [docs/aws_production_readiness.md](docs/aws_production_readiness.md).

---

## Running tests

```bash
pytest tests/ -v
```

## License

MIT. See [LICENSE](LICENSE).
