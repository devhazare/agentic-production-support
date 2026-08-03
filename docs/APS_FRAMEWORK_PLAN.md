# APS Framework Plan

## Goal

Convert this project from a single production-support application into a reusable Python framework named **APS**: **Agentic Production Support**.

Target users should be able to install the framework, import the APS library, and build their own production-support features on top of it without modifying APS internals.

Example target usage:

```python
import aps

app = (
    aps.SupportAppBuilder()
    .with_llm("openai")
    .with_vector_store("faiss")
    .with_log_source("python", path="/var/log/app.log")
    .with_agent("rca", aps.agents.RCAAgent)
    .build()
)

result = await app.handle_alert(payload)
```

Python packages are normally lowercase, so the distributable package should be `aps`, while the product/framework name can remain **APS**.

## Current State

The project already has strong framework candidates:

- Agent implementations under `agents/`
- RAG index and retrieval under `rag/`
- Workflow orchestration under `orchestration/`
- Configuration, logging, events, and exceptions under `core/`
- Domain and API models under `models/`
- LLM, embedding, AWS, audit, and integration services under `services/`
- FastAPI app under `api/`
- Dashboard under `ui/`
- Scripts, sample data, and infrastructure for demo/deployment flows

The main issue is that reusable framework code and product/demo code are currently mixed at the repository root.

## Target Architecture

Create a clean library boundary:

```text
agentic-production-support/
├── aps/
│   ├── __init__.py
│   ├── agents/
│   ├── core/
│   ├── events/
│   ├── integrations/
│   ├── llm/
│   ├── memory/
│   ├── models/
│   ├── orchestration/
│   ├── rag/
│   ├── remediation/
│   ├── telemetry/
│   └── testing/
├── aps_fastapi/
│   └── optional FastAPI adapter package
├── aps_streamlit/
│   └── optional dashboard adapter package
├── examples/
│   ├── minimal_app/
│   ├── aws_ops_app/
│   ├── magento_support/
│   └── custom_agent/
├── docs/
├── tests/
├── pyproject.toml
└── README.md
```

## Public API Design

APS should expose stable, company-facing interfaces from `aps`.

Recommended top-level imports:

```python
from aps import SupportApp, SupportAppBuilder
from aps.agents import BaseAgent, RCAAgent, RemediationAgent
from aps.models import Alert, Incident, RCAResult, RemediationPlan
from aps.rag import RAGRetriever, VectorStore
from aps.llm import LLMProvider
from aps.integrations import Integration
```

Avoid requiring users to import from deep internal modules like:

```python
from aps.core.internal.workflow_runtime import Something
```

The framework should clearly separate:

- Public APIs: stable and documented.
- Extension APIs: stable enough for company plugins.
- Internal APIs: allowed to change.

## Package Naming

Recommended package names:

- Distribution name: `agentic-production-support`
- Import package: `aps`
- Framework name: `APS`
- Long name: `Agentic Production Support`

Example install:

```bash
pip install agentic-production-support
```

Example import:

```python
import aps
```

## Core Framework Modules

### `aps.core`

Foundation module.

Should contain:

- Settings interfaces
- Logging setup
- Error hierarchy
- Runtime context
- Dependency injection helpers
- Feature flags
- Environment profiles

### `aps.models`

Domain contracts.

Should contain:

- `Alert`
- `Incident`
- `IncidentState`
- `ContextChunk`
- `RCAResult`
- `DecisionResult`
- `RemediationPlan`
- `ValidationResult`
- Pydantic request/response schemas where they are framework-level contracts

### `aps.agents`

Agent abstractions and built-in agents.

Should contain:

- `BaseAgent`
- `AgentContext`
- `IncidentDetectionAgent`
- `RCAAgent`
- `DecisionAgent`
- `RemediationAgent`
- `ValidationAgent`
- `CommunicationAgent`

Companies should be able to subclass or replace any agent.

### `aps.orchestration`

Workflow runtime.

Should contain:

- `SupportWorkflow`
- `SupportApp`
- `SupportAppBuilder`
- LangGraph-backed runtime
- Fallback local runtime
- Workflow hooks
- Middleware/interceptor support

### `aps.rag`

Retrieval-augmented generation layer.

Should contain:

- `RAGRetriever`
- `KnowledgeIndexer`
- `VectorStore` interface
- `FAISSVectorStore`
- Future adapters for OpenSearch, Chroma, Pinecone, Qdrant, Weaviate
- Document chunkers
- Source connectors
- Citation and grounding helpers

### `aps.llm`

LLM abstraction.

Should contain:

- `LLMProvider` protocol
- `LLMService`
- Provider adapters for OpenAI, Azure OpenAI, Anthropic, Bedrock, Ollama
- Retry, timeout, rate-limit, and fallback policies
- Prompt template support

### `aps.integrations`

External system adapters.

Should contain:

- Log source adapters
- Ticketing adapters
- ChatOps adapters
- Observability adapters
- Cloud provider adapters
- CMDB/change-management adapters

Initial built-in adapters can include:

- AWS
- Slack mock/live
- Jira mock/live
- Local file logs
- OpenSearch
- S3
- DynamoDB

### `aps.remediation`

Remediation execution contracts.

Should contain:

- `ActionExecutor`
- `RemediationCommand`
- `DryRunExecutor`
- `SimulatedExecutor`
- Kubernetes executor
- AWS Lambda executor
- Approval gates
- Policy checks

### `aps.telemetry`

Production visibility.

Should contain:

- Audit logging
- Metrics hooks
- Trace IDs
- Agent run history
- Evaluation records
- Safety and approval decisions

### `aps.testing`

Testing utilities for companies building on APS.

Should contain:

- Fake LLM provider
- Fake retriever
- Fake integration adapters
- Sample incidents
- Workflow test harness
- Golden-output evaluation helpers

## Extension Model

Companies should extend APS through explicit contracts.

### Custom Agent

```python
from aps.agents import BaseAgent

class CompanyRiskAgent(BaseAgent):
    async def _execute(self, incident, context):
        ...
```

### Custom Integration

```python
from aps.integrations import Integration

class ServiceNowIntegration(Integration):
    async def create_ticket(self, incident):
        ...
```

### Custom Vector Store

```python
from aps.rag import VectorStore

class CompanyVectorStore(VectorStore):
    async def search(self, query, top_k):
        ...
```

### Custom Workflow

```python
from aps import SupportAppBuilder

app = (
    SupportAppBuilder()
    .replace_agent("decision", CompanyDecisionAgent())
    .add_integration("servicenow", ServiceNowIntegration())
    .build()
)
```

## Configuration Strategy

Support three configuration layers:

1. Defaults built into APS.
2. Environment variables and `.env`.
3. User-supplied Python configuration.

Example:

```python
from aps import APSConfig, SupportAppBuilder

config = APSConfig(
    llm_provider="bedrock",
    vector_store="opensearch",
    approval_required=True,
)

app = SupportAppBuilder().with_config(config).build()
```

## Plugin Strategy

APS should support optional install extras:

```bash
pip install agentic-production-support[fastapi]
pip install agentic-production-support[streamlit]
pip install agentic-production-support[aws]
pip install agentic-production-support[opensearch]
pip install agentic-production-support[all]
```

This keeps the core framework lightweight while allowing production deployments to add only the integrations they need.

## Repository Migration Plan

### Phase 1: Define Public Contracts

- Create `aps/` package.
- Add `aps/__init__.py` with only stable exports.
- Move or wrap existing domain models under `aps.models`.
- Move `BaseAgent`, `AgentContext`, and core agent interfaces under `aps.agents`.
- Define protocols for LLM, vector store, integrations, and remediation executors.
- Keep existing app imports working temporarily through compatibility wrappers.

### Phase 2: Extract Framework Core

- Move reusable `core/`, `models/`, `agents/`, `rag/`, `orchestration/`, and reusable `services/` code into `aps/`.
- Rename app-specific code to adapter packages or examples.
- Separate framework settings from demo deployment settings.
- Remove hard-coded local paths from framework internals.
- Ensure all framework APIs accept injected dependencies.

### Phase 3: Build Adapters

- Move FastAPI code into `aps_fastapi/`.
- Move Streamlit dashboard into `aps_streamlit/`.
- Move AWS-specific implementation behind optional `aps.integrations.aws`.
- Move demo scripts into `examples/` or `tools/`.
- Keep sample apps out of the core package.

### Phase 4: Packaging

- Update `pyproject.toml`:
  - Distribution name: `agentic-production-support`
  - Import package: `aps`
  - Optional dependency groups
  - Console scripts
- Add package metadata:
  - License
  - Authors
  - Keywords
  - Classifiers
  - Python version support
- Add build validation:
  - `python -m build`
  - Install from wheel in a clean virtualenv
  - Import smoke test

### Phase 5: Developer Experience

- Add quickstart examples.
- Add generated API documentation.
- Add extension guides.
- Add production deployment guide.
- Add migration guide from current repo layout to APS.
- Add reference architecture diagrams.

### Phase 6: Production Hardening

- Add stable semantic versioning.
- Add changelog.
- Add deprecation policy.
- Add security policy.
- Add structured audit trail for every agent decision.
- Add policy gates before remediation.
- Add evaluation harness for RCA quality.
- Add integration tests for each optional adapter.

## Backward Compatibility Plan

During migration, keep thin compatibility modules at the old paths:

```python
# agents/rca/__init__.py
from aps.agents.rca import RCAAgent
```

This allows current project code to continue running while the reusable framework package is introduced.

After the framework stabilizes, old root-level modules can be removed in a major version.

## Proposed Public Classes

Minimum stable API for version `0.1.0`:

- `aps.SupportApp`
- `aps.SupportAppBuilder`
- `aps.APSConfig`
- `aps.AgentContext`
- `aps.agents.BaseAgent`
- `aps.agents.RCAAgent`
- `aps.agents.RemediationAgent`
- `aps.rag.RAGRetriever`
- `aps.rag.VectorStore`
- `aps.rag.FAISSVectorStore`
- `aps.llm.LLMProvider`
- `aps.llm.LLMService`
- `aps.integrations.Integration`
- `aps.remediation.ActionExecutor`

## First Release Scope

Version `0.1.0` should focus on framework usability, not every possible integration.

Include:

- Core agent contracts
- Default incident workflow
- RAG with FAISS
- LLM abstraction
- OpenAI/Ollama provider support
- Dry-run and simulated remediation
- FastAPI adapter as optional extra
- Minimal example application
- Extension examples

Defer:

- Full cloud marketplace packaging
- All ticketing systems
- All vector databases
- Complex multi-tenant features
- Advanced UI customization

## Acceptance Criteria

The framework migration is successful when a new company can:

1. Install APS in a fresh Python project.
2. Import `aps`.
3. Configure an LLM and vector store.
4. Register its own log source or alert payload.
5. Run the default support workflow.
6. Replace at least one built-in agent with a company-specific agent.
7. Run without importing from private/internal modules.
8. Use FastAPI or another interface as an adapter, not as the core runtime.
9. Run tests with fake LLM and fake retriever implementations.
10. Upgrade APS versions with clear release notes and minimal breaking changes.

## Recommended Immediate Next Steps

1. Create `aps/` as the new library root.
2. Add `aps/__init__.py` with planned public exports.
3. Add interface/protocol modules before moving implementations.
4. Move reusable code gradually, starting with models and base agent contracts.
5. Add compatibility wrappers for old imports.
6. Update tests to import from `aps`.
7. Update `pyproject.toml` for package distribution.
8. Create a minimal external example that imports APS as a dependency.

## Key Design Principle

APS should be a framework, not a fixed application.

The framework should provide reliable defaults, but every production company must be able to replace:

- LLM provider
- RAG backend
- Incident detector
- RCA agent
- Decision policy
- Approval workflow
- Remediation executor
- Communication channel
- Audit sink
- API/UI layer

without editing APS source code.
