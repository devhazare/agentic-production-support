# Database Connection Pool Exhaustion Runbook

Symptoms include HikariPool timeout, active connections near max, elevated request queue depth,
and slow checkout or order APIs.

Recommended response:
- Verify leaked transactions and long-running queries.
- Temporarily scale service workers only if database capacity allows it.
- Roll back code if exhaustion follows a deployment.

Safe MVP action: scale_service_mock.

