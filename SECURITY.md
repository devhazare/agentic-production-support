# Security Policy

## Supported Use

Agentic Support Framework is currently an MVP/reference implementation for AI
Operations and Production Support workflows.

Recommended default mode:

```env
APP_MODE=mock
USE_AWS=false
```

In this mode, the project avoids external LLM calls and cloud service calls.
Remediation remains simulated.

## Current Security Limitations

The current codebase does not provide:

- API authentication.
- Role-based authorization.
- Production approval identity management.
- Real secret-management integration.
- Production-grade remediation guardrails.
- Full prompt-injection protection.
- Complete PII detection.

Do not expose this API publicly without adding appropriate security controls.

## Reporting a Vulnerability

Please do not open public issues for:

- Credential exposure.
- Exploitable security bugs.
- Prompt-injection bypasses.
- Privilege-escalation paths.
- Sensitive data disclosure.

Report privately to the repository owner or maintainer. Include:

- Affected component or endpoint.
- Reproduction steps.
- Impact.
- Suggested mitigation, if known.
- Whether any secret or private data was exposed.

## Secret Handling

Never commit:

- `.env`
- API keys
- Cloud credentials
- OAuth tokens
- Slack/Jira tokens
- Private keys
- Terraform state
- Production logs
- Customer or personal data

If a real secret was committed, deleting it from the current file is not enough.
Rotate the credential and remove it from Git history before publishing.

## Public Release Checklist

Before publishing a fork or derivative project:

- Run a secret scan over the working tree and Git history.
- Confirm `.env` is ignored and not staged.
- Confirm local state under `.local/` is not staged.
- Confirm Terraform state files are not staged.
- Confirm generated FAISS index and pickle files are not staged.
- Confirm generated logs are not staged.
- Review sample data for private information.
- Review Postman collections and scripts for concrete private URLs.

## Responsible AI Notes

This project uses LLMs for summarization, RCA, and remediation-plan generation.
Operators should review generated output before relying on it. High-risk actions
should require human approval and independent verification.
