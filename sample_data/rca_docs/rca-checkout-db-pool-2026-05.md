# RCA Checkout Database Pool 2026-05

Root cause: checkout-api exhausted database connections after a traffic spike and long-running order lookup query.
Evidence: HikariPool timeouts, p99 latency above 4 seconds, database connections above 95 percent.
Resolution: increased worker pool cautiously, fixed query index, and added pool saturation alert.

