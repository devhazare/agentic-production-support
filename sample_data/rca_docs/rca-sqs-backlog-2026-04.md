# RCA SQS Backlog 2026-04

Root cause: email-consumer processing rate dropped below producer rate after downstream email vendor throttling.
Evidence: queue visible messages rose to 22000 and oldest message age exceeded 20 minutes.
Resolution: drained queue with controlled concurrency and paused noncritical producers.

