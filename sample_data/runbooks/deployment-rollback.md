# Deployment Rollback Runbook

Use when error rate or latency regresses immediately after a release.

Checks:
- Confirm regression correlates with deployment timestamp.
- Compare new error signatures against previous version.
- Confirm rollback target is the last known healthy version.

Safe MVP action: rollback_deployment_mock. High and Critical incidents require approval before any action.

