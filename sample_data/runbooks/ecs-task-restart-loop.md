# ECS Task Restart Loop Runbook

Common causes: failing readiness probe, bad environment variable, dependency outage, or container crash.

Checks:
- Review task stopped reason and last container logs.
- Compare current task definition with previous healthy revision.
- Validate health check endpoint and dependency credentials.

Safe MVP action: restart_service_mock for transient runtime failure; rollback_deployment_mock if a new task definition caused the loop.

