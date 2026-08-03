# Open Source Readiness Report

Date reviewed: 2026-07-27

This report reviews the project for public Git/GitHub release and developer reuse.
It is intentionally action-oriented so cleanup can happen one step at a time.

## Executive Summary

The project is a solid MVP/demo candidate, but it should not be pushed publicly as-is.

Main reasons:

- The directory is not currently initialized as a Git repository.
- The working tree contains local/private/generated artifacts that should not be published.
- There is no open-source license file.
- The test suite is not currently green in the active local environment.
- Some documentation and dependency details are inconsistent.

Recommended release posture: publish as an "AI Ops / Agentic Support Framework MVP" with clear boundaries:

- Local mock mode works without cloud credentials.
- Remediation is dry-run/mock only.
- AWS/Bedrock/OpenSearch/Terraform pieces are optional reference infrastructure.
- RAG is custom FAISS-based, while orchestration uses LangGraph from the LangChain ecosystem.

## Current Repository State

Observed state:

- `git status` fails with: `fatal: not a git repository`.
- First-party Python files compile successfully with `python -m compileall`.
- Active venv test command fails with configured coverage options.
- Tests can be collected by disabling `pyproject.toml` addopts, but 4 tests fail.

Approximate first-party file count after excluding `.venv`, `.terraform`, Terraform build output, IDE folders, and pytest cache: 196 files.

Approximate size after those exclusions: 127 MB.

Largest first-party artifacts:

- `data/faiss_index_meta.pkl`: 67 MB
- `data/knowledge_base/fixed_issues.md`: 28 MB
- `data/knowledge_base/issues.psv`: 25 MB
- `data/faiss_index_embedder.pkl`: 800 KB
- `data/faiss_index.index`: 632 KB
- `sample_logs/magento/*.log`: about 2 MB total

## Must Fix Before Public Push

### 1. Add a License

No `LICENSE` file was found.

Without a license, external developers do not have clear legal permission to use, modify, or redistribute the code.

Recommended options:

- MIT: simplest and permissive.
- Apache-2.0: permissive with explicit patent grant.

For a developer-friendly open-source release, MIT is usually enough unless you want stronger patent language.

### 2. Remove or Ignore Local Secrets and Private State

Files currently present that should not be pushed:

- `.env`
- `.claude/settings.local.json`
- `.idea/`
- `.local/`
- `.pytest_cache/`
- `.venv/`
- `__pycache__/`
- `*.pyc`
- `terraform.tfstate`
- `infra/terraform/terraform.tfstate`
- `infra/terraform/terraform.tfstate.backup`
- `infra/terraform/.terraform/`
- `infra/terraform/build/`
- `sample_app/logs/app.log`

The current `.gitignore` covers some of these, but not all:

- It ignores `.local/`, `.pytest_cache/`, `__pycache__/`, `*.pyc`, `.venv/`, `infra/terraform/.terraform/`, `infra/terraform/build/`, and `infra/terraform/*.tfstate*`.
- It does not ignore `.env`.
- It does not ignore `.idea/`.
- It does not ignore root-level `terraform.tfstate`.
- It does not ignore runtime log files like `*.log`.
- It does not ignore generated FAISS binary artifacts.

Recommended `.gitignore` additions:

```gitignore
.env
.idea/
.DS_Store
*.log
*.tfstate
*.tfstate.*
data/faiss_index*
```

Keep `.env.example` in the repo. Do not keep `.env`.

### 3. Decide What to Do With Large Data Artifacts

The repo includes large generated and knowledge files:

- `data/faiss_index_meta.pkl`
- `data/faiss_index_embedder.pkl`
- `data/faiss_index.index`
- `data/knowledge_base/fixed_issues.md`
- `data/knowledge_base/issues.psv`

Risks:

- Large initial clone size.
- Pickle files are not ideal for public distribution because loading pickle is unsafe with untrusted files.
- Large knowledge files may contain synthetic or copied content that should be reviewed for provenance before publishing.

Recommended approach:

- Do not commit generated FAISS index files.
- Keep a small curated sample knowledge base in Git.
- Document how to rebuild the index with `scripts/ingest_knowledge.py` or the RAG rebuild endpoint.
- If the large knowledge files are important, move them to a release asset or separate dataset repo after checking licensing and sanitization.

### 4. Fix Test Execution

Running:

```bash
.venv/bin/pytest tests/ -q
```

currently fails before collection:

```text
pytest: error: unrecognized arguments: --cov-omit=tests/*
```

This comes from `pyproject.toml`:

```toml
addopts = "--cov=. --cov-report=term-missing --cov-omit=tests/*"
```

Likely cause: `pytest-cov` is not installed or not active in the current venv.

Running without project addopts:

```bash
.venv/bin/pytest tests/ -q -o addopts=''
```

collects tests but fails 4 tests:

- `tests/unit/test_agents.py::TestSeverityScorer::test_service_down_is_critical`
- `tests/unit/test_agents.py::TestSeverityScorer::test_high_cpu_is_high`
- `tests/unit/test_agents.py::TestIncidentDetectionAgent::test_creates_incident_with_correct_service`
- `tests/unit/test_agents.py::TestIncidentDetectionAgent::test_invalid_severity_raises`

Actual behavior:

- `ServiceDown` scores `HIGH`, but test expects `CRITICAL`.
- CPU 92 scores `MEDIUM`, but test expects `HIGH`.
- Invalid severity is rejected by Pydantic schema before the agent-level `IncidentDetectionError` expectation.

Recommended fixes:

- Decide whether the severity scorer or tests represent the desired behavior.
- If `ServiceDown` must always be critical, make that an explicit scorer rule.
- If CPU above 90 should be high, adjust the points threshold or test expectation.
- Update invalid severity test to expect Pydantic validation, or relax schema validation and keep agent-level validation.
- Reinstall dependencies from `requirements.txt` and confirm `pytest-cov` is available.

### 5. Add `.dockerignore`

No `.dockerignore` file was found.

Because the Dockerfile uses:

```dockerfile
COPY . .
```

Docker builds can accidentally include `.env`, `.venv`, `.idea`, Terraform state, logs, cache files, and generated data.

Recommended `.dockerignore`:

```dockerignore
.env
.venv/
.idea/
.pytest_cache/
__pycache__/
*.pyc
*.log
.local/
infra/terraform/.terraform/
infra/terraform/build/
*.tfstate
*.tfstate.*
data/faiss_index*
```

## Should Fix Before LinkedIn Announcement

### 1. Update README Positioning

The README is strong technically, but for public developers it should start with:

- What the project does in one paragraph.
- What works locally without cloud services.
- Quick demo commands.
- Architecture diagram or flow summary.
- Safety note: remediation is mock/dry-run only.
- Screenshots or GIFs of the dashboard/API flow if available.

Current README emphasizes design patterns heavily before practical usage. For external developers, lead with outcome and quick start, then architecture.

### 2. Add Contribution and Security Docs

Recommended files:

- `CONTRIBUTING.md`
- `SECURITY.md`
- `CODE_OF_CONDUCT.md` if you expect community contributions.

Minimum useful `CONTRIBUTING.md` should include:

- Python version: 3.11
- Setup commands
- Test command
- Style/lint command
- Branch/PR expectations
- How to add new agents, log parsers, or RAG documents

### 3. Add a Public Roadmap

A short `ROADMAP.md` would help developers understand where to contribute.

Suggested sections:

- Real Slack/Jira integrations
- Production remediation approval workflow
- LangSmith tracing
- OpenTelemetry
- More log parser plugins
- Pluggable vector stores
- CI/CD
- Multi-tenant auth

### 4. Fix Documentation Inconsistency

`requirements.txt` has:

```text
langgraph==0.2.39
```

`docs/RAG_LANGCHAIN_IMPLEMENTATION.md` says:

```text
langgraph==0.2.74
```

Pick one and update docs/dependencies so developers do not install a mismatched runtime.

### 5. Add CI

Recommended GitHub Actions workflow:

- Set up Python 3.11
- Install `requirements.txt`
- Run `python -m compileall`
- Run `pytest`
- Optionally run Ruff and mypy after configuration is cleaned up

Do this before announcing if possible; a public repo with a visible passing CI badge builds trust quickly.

## Security and Safety Notes

### CORS

`api/main.py` currently allows all origins:

```python
allow_origins=["*"]
```

Fine for local demo. Not safe as-is for a production API.

Recommendation:

- Keep permissive CORS in local mode.
- Make production origins configurable.

### Terraform

Terraform state files should never be committed.

Even small state files can expose:

- AWS account IDs
- resource names
- ARNs
- generated secrets
- infrastructure topology

Recommendation:

- Delete local state files before Git init.
- Commit only `.tf` source files and `.terraform.lock.hcl` if desired.
- Document remote state setup for real deployments.

### Pickle Files

Generated `*.pkl` files should generally not be committed.

Reason:

- Pickle is executable during load.
- Public developers should rebuild artifacts from source data.

## Code Quality Notes

Strengths:

- Clear modular layout: `agents`, `orchestration`, `rag`, `services`, `api`, `models`, `tests`.
- Good typed configuration via Pydantic settings.
- Local mock mode makes the project approachable.
- LangGraph workflow has a local fallback graph.
- RAG stack can run with FAISS and local embeddings.
- Tests cover important agent and workflow paths.

Gaps:

- Test suite is not currently green.
- Some README claims are more polished than the current state supports.
- Generated build folders and runtime artifacts are mixed into the project directory.
- No packaging metadata beyond minimal `pyproject.toml`.
- No CI workflow.
- No open-source governance files.
- No dependency lock strategy beyond pinned `requirements.txt`.
- No `.dockerignore`.

## Suggested Cleanup Order

1. Add/expand ignore files: `.gitignore` and `.dockerignore`.
2. Remove local-only files from the publish tree: `.env`, `.idea/`, `.local/`, caches, logs, Terraform state, generated FAISS artifacts.
3. Add `LICENSE`.
4. Fix test environment and failing tests.
5. Align docs with actual dependencies and behavior.
6. Rewrite top of README for public developer onboarding.
7. Add `CONTRIBUTING.md`, `SECURITY.md`, and optionally `ROADMAP.md`.
8. Initialize Git and make a clean first commit.
9. Create GitHub repo and push.
10. Add GitHub Actions CI.
11. Prepare LinkedIn post with honest MVP scope and repo link.

## Suggested GitHub Description

Agentic AI Ops framework for incident detection, RAG-grounded RCA, LangGraph orchestration, approval gates, and mock remediation with FastAPI, Streamlit, FAISS, and optional AWS Bedrock/OpenSearch integrations.

## Suggested LinkedIn Positioning

Short version:

> I open-sourced an Agentic AI Ops framework for incident detection, RAG-grounded RCA, LangGraph-based workflow orchestration, approval gates, and dry-run remediation. It runs locally in mock mode, includes FastAPI APIs, a Streamlit dashboard, FAISS-backed retrieval, sample incidents/runbooks, and optional AWS Bedrock/OpenSearch deployment scaffolding.

Important to say:

- It is an MVP/reference implementation.
- Remediation is mock/dry-run by design.
- The goal is to help developers learn and extend agentic operations workflows safely.

Avoid saying:

- "Production ready" without qualifying what is production-ready.
- "Autonomous remediation" without saying it is dry-run/mock.
- "LangChain RAG" if the retriever is custom FAISS rather than LangChain retriever abstractions.

Better phrasing:

- "LangGraph orchestration from the LangChain ecosystem."
- "Custom FAISS-backed RAG layer."
- "Safe mock remediation flow."

## Release Checklist

- [ ] Add `LICENSE`.
- [ ] Add `.dockerignore`.
- [ ] Expand `.gitignore`.
- [ ] Remove `.env` from publish tree.
- [ ] Remove IDE/cache/runtime artifacts.
- [ ] Remove Terraform state files.
- [ ] Remove generated FAISS pickle/index files or move to release assets.
- [ ] Review large knowledge files for license/provenance/privacy.
- [ ] Fix test command and failing tests.
- [ ] Align LangGraph version in docs and requirements.
- [ ] Improve README quick start and public positioning.
- [ ] Add contribution/security docs.
- [ ] Initialize Git.
- [ ] Push to GitHub.
- [ ] Add CI.
- [ ] Draft LinkedIn post after repo link is live.
