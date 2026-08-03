# Checkout API Latency Runbook

Signals: p99 latency, database connection wait time, 5xx rate, downstream payment latency.

First checks:
- Confirm whether latency is concentrated around database connection acquisition.
- Compare current connection pool usage against configured max.
- Review recent deployments and feature flags.

Safe MVP action: scale_service_mock when pool saturation is the primary evidence.

