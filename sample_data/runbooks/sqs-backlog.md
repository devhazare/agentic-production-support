# SQS Queue Backlog Runbook

Signals: ApproximateNumberOfMessagesVisible rising, oldest message age increasing, consumer lag.

Checks:
- Confirm consumers are healthy and not throttled.
- Check downstream API latency and DLQ growth.
- Increase consumer concurrency only within downstream rate limits.

Safe MVP action: drain_queue_mock.

