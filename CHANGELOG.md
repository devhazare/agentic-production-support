# Changelog

All notable changes to this project will be documented in this file.

This project follows a simple date-based changelog until formal releases are
introduced.

## Unreleased

### Added

- Public README with architecture, quick start, capability status, RAG/LLM
  behavior, limitations, and contribution links.
- Documentation for architecture, configuration, API routes, RAG/LLM behavior,
  local operations, and project release status.
- GitHub issue templates, pull request template, support guide, security policy,
  and code of conduct.

### Documented

- Default mock mode and safe local operation.
- Implemented, partial, mocked, experimental, planned, and unavailable
  capabilities.
- Local FAISS RAG and default embedding model `all-MiniLM-L6-v2`.
- TF-IDF fallback behavior for offline embedding.
- Simulated remediation and human approval behavior.
- Public release cleanup risks.

### Known Limitations

- No API authentication or authorization.
- Real Slack/Jira delivery is not implemented.
- Real infrastructure remediation is not implemented.
- OpenAI, Anthropic, and Azure OpenAI provider modules are not present.
- Production deployment hardening remains future work.
