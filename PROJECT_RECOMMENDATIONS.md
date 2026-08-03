# Project Recommendations

This document lists recommended capabilities that would make the Agentic Support Framework more useful for developers, demos, and real-world incident workflows.

## Must-Have Product Capabilities

### 1. RAG-Based Incident Triage UI

Build a dedicated triage screen in the Streamlit dashboard for active incidents.

Recommended UI sections:

- Incident summary: service, severity, alert type, status, timestamp, owner.
- Timeline: detection, retrieval, RCA, decision, approval, remediation, validation.
- Retrieved context: runbooks, past incidents, log patterns, RCA docs.
- RCA explanation: root cause, evidence, confidence, citations.
- Suggested next action: approve, reject, ask for more info, monitor only.
- Risk panel: blast radius, rollback risk, customer impact, confidence.
- Human notes: reviewer comments and final decision.

Why this matters:

- Developers and SREs need to see why the agent made a recommendation.
- RAG output without citations is hard to trust.
- A triage UI turns the project from an API demo into an operational tool.

### 2. Query Rewrite for RAG Retrieval

Add a query rewrite step before vector search.

Current likely behavior:

- Incident fields are directly converted into a retrieval query.

Recommended behavior:

- Convert noisy alert/log input into 2-4 clean search queries.
- Include service name, alert type, metric symptoms, error signatures, and suspected subsystem.
- Generate alternate queries for past incidents, runbooks, and remediation docs.

Example:

Raw incident:

```text
checkout-api p99 latency 4200ms, database connection acquisition timeouts
```

Rewritten queries:

```text
checkout-api database connection pool timeout runbook
high p99 latency caused by DB connection exhaustion
past incident checkout latency HikariPool timeout
safe remediation for database connection pool saturation
```

Recommended implementation:

- Add `rag/query_rewriter.py`.
- Use deterministic rewrite rules in mock mode.
- Use LLM rewrite only in live mode.
- Store rewritten queries in incident state for auditability.

### 3. RAG Retrieval Quality Score

Add a retrieval confidence score before RCA generation.

Recommended signals:

- Top result similarity score.
- Gap between top result and lower-ranked results.
- Number of usable chunks above threshold.
- Citation diversity across files.
- Presence of exact error signature match.
- Whether a matching runbook exists.

Suggested output:

```json
{
  "retrieval_score": 0.82,
  "top_k": 4,
  "usable_chunks": 3,
  "exact_signature_match": true,
  "citation_files": [
    "runbooks/database-connection-pool.md",
    "rca_docs/rca-checkout-db-pool-2026-05.md"
  ]
}
```

Why this matters:

- The RCA agent should know when retrieved context is weak.
- Low retrieval score should force human review or ask for more info.

### 4. RCA Validation Score

Add a post-RCA validation step that scores whether the RCA is grounded and actionable.

Recommended score dimensions:

- Evidence grounding: RCA claims are supported by retrieved context.
- Log alignment: explanation matches observed log snippets.
- Metric alignment: explanation matches metric anomalies.
- Action validity: recommended action is supported and allowed.
- Risk fit: action risk matches incident severity and blast radius.
- Citation quality: references are specific and relevant.

Suggested model:

```json
{
  "validation_score": 0.88,
  "grounding_score": 0.91,
  "actionability_score": 0.84,
  "risk_score": 0.27,
  "passed": true,
  "reasons": [
    "RCA references matching DB timeout runbook",
    "Recommended scale action is allowed for medium risk",
    "Metrics align with connection saturation"
  ]
}
```

Routing rule:

- `validation_score >= 0.80`: allow normal decision flow.
- `0.60 <= validation_score < 0.80`: require human review.
- `< 0.60`: mark as needs more information.

### 5. Citation-Aware RCA

Every RCA should include citations to retrieved context.

Recommended requirements:

- At least one citation for each main claim.
- At least one runbook or past incident citation for remediation.
- Citation IDs should map to exact retrieved chunks.

Suggested RCA shape:

```json
{
  "root_cause": "...",
  "evidence": [
    {
      "claim": "DB pool saturation caused checkout latency",
      "citation_id": "chunk_003",
      "source": "sample_data/runbooks/database-connection-pool.md"
    }
  ],
  "recommended_action": "scale_service_mock",
  "confidence": 0.86
}
```

### 6. Human Approval Workbench

Improve approval from a simple endpoint into a workbench.

Recommended capabilities:

- Queue of incidents requiring approval.
- Side-by-side view of RCA, retrieved evidence, and proposed action.
- Approve/reject/needs-more-info buttons.
- Required comment for high-risk approvals.
- Approval audit trail.
- Display previous similar incidents and outcomes.

### 7. Incident Similarity Search

Add a "similar incidents" panel.

Recommended matching inputs:

- Service name
- Alert type
- Log signature
- Metric pattern
- RCA category
- Remediation action

Why this matters:

- Similar historical incidents are often more useful than generic runbooks.
- This makes the RAG system operationally credible.

### 8. Feedback Loop for Learning

Capture human feedback after incident resolution.

Recommended feedback fields:

- Was RCA correct?
- Was recommended action useful?
- Was severity correct?
- Did the incident need escalation?
- Final root cause.
- Final remediation.
- Time to resolve.

Use feedback to:

- Improve future retrieval.
- Add resolved incidents to the knowledge base.
- Tune decision thresholds.
- Identify weak runbooks.

## Must-Have Engineering Capabilities

### 1. Clean Open-Source Repository Hygiene

Before publishing:

- Add `LICENSE`.
- Add `.dockerignore`.
- Expand `.gitignore`.
- Remove `.env`, Terraform state, local logs, caches, venv, and generated FAISS artifacts.
- Keep only safe sample data.

### 2. Passing Tests and CI

Required:

- Fix failing unit tests.
- Ensure `pytest` works without local hacks.
- Add GitHub Actions for Python 3.11.
- Run compile, tests, and optionally lint.

Recommended CI jobs:

- Unit tests.
- API smoke test.
- RAG index build smoke test.
- Docker build.

### 3. Better Developer Onboarding

README should include:

- One-paragraph value proposition.
- Architecture diagram.
- 5-minute quick start.
- Local mock mode demo.
- Streamlit dashboard screenshot.
- API examples.
- Safety disclaimer.
- Contribution guide.

### 4. Dependency Cleanup

Current recommendation:

- Align LangGraph version across docs and requirements.
- Decide whether full `langchain` is required or only `langchain-core` plus `langgraph`.
- Split dependencies into:
  - `requirements.txt`
  - `requirements-dev.txt`
  - `requirements-lambda.txt`

Suggested dev dependencies:

```text
pytest
pytest-asyncio
pytest-cov
ruff
mypy
pre-commit
```

### 5. Config Validation and Profiles

Add explicit config profiles:

- `local-mock`
- `local-ollama`
- `aws-bedrock`
- `production`

Recommended behavior:

- Fail fast if `USE_AWS=true` but required AWS settings are missing.
- Warn if production uses permissive CORS.
- Warn if remediation is enabled without approval rules.

### 6. Public API Stability

Add versioned request/response examples for:

- Incident trigger
- RAG search
- RAG rebuild
- Approval
- Rejection
- Dashboard data

Recommended:

- Keep OpenAPI docs.
- Add API contract tests.
- Add Postman collection validation.

## Recommended Agent Workflow Enhancements

### 1. Explicit Triage Agent

Add a dedicated `triage_agent` between detection and retrieval.

Responsibilities:

- Normalize alert context.
- Identify affected service and subsystem.
- Classify incident category.
- Extract error signatures.
- Estimate urgency.
- Decide which knowledge sources to query.

Suggested workflow:

```text
incident_agent
  -> triage_agent
  -> query_rewrite_agent
  -> retrieval_agent
  -> rca_agent
  -> validation_agent
  -> decision_agent
  -> approval_agent
  -> remediation_agent
  -> communication_agent
  -> learning_agent
```

### 2. Query Rewrite Agent

Responsibilities:

- Generate multiple retrieval queries.
- Preserve original query.
- Score rewritten queries.
- Avoid hallucinated service names or technologies.

### 3. Retrieval Validation Agent

Responsibilities:

- Check whether retrieved chunks are relevant.
- Drop weak chunks.
- Detect missing context.
- Ask for more info when retrieval quality is low.

### 4. RCA Critic Agent

Responsibilities:

- Challenge RCA claims.
- Check citation support.
- Check recommended action safety.
- Produce validation score.

### 5. Policy Agent

Responsibilities:

- Enforce remediation policy.
- Block unsafe actions.
- Require human approval based on severity, risk, and confidence.
- Maintain allowlist of supported actions.

## Recommended Data Model Additions

Add fields to incident state:

```python
rewritten_queries: list[str]
retrieval_score: float
retrieval_diagnostics: dict
citations: list[Citation]
rca_validation_score: float
rca_validation_reasons: list[str]
similar_incidents: list[SimilarIncident]
human_feedback: HumanFeedback | None
```

Suggested models:

```python
class Citation(BaseModel):
    citation_id: str
    source: str
    chunk_id: str
    text_preview: str
    relevance_score: float

class SimilarIncident(BaseModel):
    incident_id: str
    service: str
    summary: str
    resolution: str
    similarity_score: float

class HumanFeedback(BaseModel):
    rca_correct: bool
    action_useful: bool
    final_root_cause: str | None = None
    final_remediation: str | None = None
    reviewer: str
    comment: str
```

## Recommended RAG Improvements

### 1. Hybrid Retrieval

Use both:

- Vector search for semantic similarity.
- Keyword/BM25 search for exact error signatures.

Why:

- Logs often contain exact tokens that embeddings miss.
- Error codes, exception names, and IDs are better handled with lexical search.

### 2. Chunk Metadata

Each chunk should include:

- Source path
- Document type: runbook, RCA, incident, log pattern
- Service
- Alert type
- Severity
- Last updated
- Owner
- Tags

### 3. Reranking

Add a lightweight reranker after initial retrieval.

Options:

- Rule-based reranking in mock mode.
- Cross-encoder reranking in local mode.
- LLM reranking in live mode.

### 4. Knowledge Freshness

Display freshness:

- When the index was built.
- Number of documents indexed.
- Number of chunks.
- Stale documents.
- Failed documents.

### 5. Knowledge Upload UI

Allow users to upload:

- Runbooks
- RCA docs
- Incident postmortems
- Known error patterns

UI should show:

- Parsing status
- Chunk count
- Index rebuild status
- Search preview

## Recommended Dashboard Views

### 1. Triage Queue

Primary screen for active incidents.

Columns:

- Severity
- Service
- Alert type
- Status
- RCA confidence
- Validation score
- Retrieval score
- Age
- Action required

### 2. Incident Detail

Detailed operational view:

- Incident metadata
- Agent timeline
- Logs and metrics
- Rewritten queries
- Retrieved evidence
- RCA
- Validation score
- Decision
- Approval controls
- Remediation result
- Audit trail

### 3. RAG Explorer

Developer-facing RAG debugging view:

- Enter query
- See rewritten queries
- View top chunks
- See relevance scores
- Inspect citations
- Compare vector vs keyword results

### 4. Knowledge Base Admin

Admin view:

- Upload docs
- Rebuild index
- Check stale docs
- Delete docs
- See document coverage by service

### 5. Evaluation Dashboard

Measure quality:

- RCA correctness rate
- Approval rate
- Auto-remediation rate
- Retrieval hit rate
- Validation pass rate
- False positive rate
- Mean time to triage
- Mean time to resolution

## Recommended Safety Controls

### 1. Dry-Run by Default

Keep all remediation dry-run by default.

Production action execution should require:

- Explicit config flag.
- Human approval.
- Action allowlist.
- Audit logging.
- Rollback plan.

### 2. Policy-Based Routing

Suggested rules:

- Critical severity always requires human approval.
- Low validation score requires more information.
- Low retrieval score prevents auto-remediation.
- Unknown service prevents remediation.
- Missing rollback plan prevents remediation.

### 3. Audit Trail

Every decision should record:

- Agent name
- Input summary
- Output summary
- Timestamp
- Confidence
- Validation score
- Human actor, if any

## Recommended Priority Roadmap

### Phase 1: Publish-Ready Cleanup

- Add license.
- Clean ignored files.
- Fix tests.
- Add `.dockerignore`.
- Improve README.

### Phase 2: Triage Quality

- Add query rewrite.
- Add retrieval score.
- Add RCA validation score.
- Add citation-aware RCA.
- Add similar incidents.

### Phase 3: UI Upgrade

- Build RAG-based incident triage UI.
- Add RAG explorer.
- Add approval workbench.
- Add knowledge base admin.

### Phase 4: Production Hardening

- Add CI.
- Add config profiles.
- Add OpenTelemetry.
- Add real Slack/Jira integration.
- Add auth.
- Add policy engine.

### Phase 5: Evaluation and Learning

- Add feedback capture.
- Add RCA evaluation dataset.
- Add retrieval evaluation.
- Track quality metrics over time.

## Best Next Feature to Build

The highest-impact next feature is:

> RAG-based Incident Triage UI with rewritten queries, retrieved citations, RCA validation score, and approval controls.

Why:

- It makes the project immediately understandable in demos.
- It exposes the agent reasoning process.
- It helps developers debug retrieval and RCA quality.
- It gives the LinkedIn launch a clear visual story.

Recommended first implementation scope:

- Add triage queue table.
- Add incident detail panel.
- Show rewritten queries.
- Show retrieved chunks with scores.
- Show RCA and validation score.
- Add approve/reject/needs-more-info actions.
