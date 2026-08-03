# Security Policy

## Supported Use

This project is published as an AI operations MVP and reference implementation.
Local mock mode is the recommended default for demos and development.

Automated remediation integrations are mock or dry-run oriented unless you
explicitly connect cloud credentials and production systems.

## Reporting a Vulnerability

Please do not open public issues for secrets, credential exposure, or exploitable
security bugs.

Report security concerns privately to the repository owner. Include:

- Affected component or endpoint
- Reproduction steps
- Impact
- Suggested mitigation, if known

## Public Release Checklist

Before publishing forks or derivative projects, verify that these files are not
committed:

- `.env`
- Cloud credentials
- Terraform state files
- Local logs
- IDE settings
- Generated FAISS pickle/index artifacts
