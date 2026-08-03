# Agentic Production Support Framework Plan

This plan reflects the current project direction.

## Current Foundation

- FastAPI incident APIs.
- Streamlit dashboard.
- Detection, RCA, decision, remediation, validation, and communication agents.
- Local FAISS RAG.
- Mock LLM and Ollama path.
- Human approval flow.
- Simulated remediation.
- Local and optional cloud persistence paths.

## Next Engineering Milestones

1. Add API authentication and authorization.
2. Add real notification adapters.
3. Add production-grade approval identity and audit controls.
4. Implement live verification adapters.
5. Add reviewed remediation executors with dry-run and rollback support.
6. Add CI/CD, dependency scanning, and secret scanning.
7. Add provider modules for configured cloud LLM providers or remove unsupported
   provider settings.
8. Add a learning workflow for approved incident outcomes.
