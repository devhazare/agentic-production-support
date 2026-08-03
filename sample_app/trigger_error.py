"""
sample_app/trigger_error.py
----------------------------
Deliberately writes error patterns to app.log that match the framework's
anomaly detection rules and trigger a real incident + RAG-backed RCA.

Usage:
    python sample_app/trigger_error.py               # interactive menu
    python sample_app/trigger_error.py --scenario 1  # direct run
"""

from __future__ import annotations

import argparse
import logging
import time
import sys
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S,%f",
    handlers=[
        logging.FileHandler(LOG_DIR / "app.log", mode="a", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

log = logging.getLogger("sample-app")


# ── Scenario 1: CUDA / GPU out of memory ─────────────────────────────────────
# Triggers rule: "CUDA OOM" (threshold=3, window=600s)
# Maps to RAG chunks: INC-2024-L03 (CUDA OOM batch size fix)
def scenario_cuda_oom(repeat: int = 4) -> None:
    print(f"\n[Scenario 1] Firing CUDA OOM × {repeat} — triggers in ~5s after 3rd hit")
    for i in range(repeat):
        log.critical(
            "torch.cuda.OutOfMemoryError: CUDA out of memory. "
            "Tried to allocate 2.50 GiB. "
            "Allocated: 7.8GiB / 8.0GiB on ml-inference device=cuda:0"
        )
        print(f"  wrote CUDA OOM error {i + 1}/{repeat}")
        time.sleep(0.5)


# ── Scenario 2: DB connection pool exhaustion ─────────────────────────────────
# Triggers rule: "DB connection exhaustion" (threshold=5, window=300s)
# Maps to RAG chunks: INC-2024-003 (HikariPool fix)
def scenario_db_exhaustion(repeat: int = 6) -> None:
    print(f"\n[Scenario 2] Firing DB connection errors × {repeat}")
    for i in range(repeat):
        log.error(
            "requests.exceptions.ConnectionError: "
            "DBPool Connection is not available, request timed out after 30000ms. "
            "Active:25 Idle:0 Max:25 on order-service"
        )
        print(f"  wrote DB error {i + 1}/{repeat}")
        time.sleep(0.3)


# ── Scenario 3: Kafka consumer lag ────────────────────────────────────────────
# Triggers rule: "Error rate spike" (20 errors in 5min) or specific Kafka rule
# Maps to RAG chunks: INC-2024-L06 (Kafka consumer threading fix)
def scenario_kafka_lag(repeat: int = 5) -> None:
    print(f"\n[Scenario 3] Firing Kafka consumer lag warnings × {repeat}")
    for i in range(repeat):
        log.warning(
            "data-pipeline - Kafka consumer lag at 8240 messages "
            "(threshold: 5000). Topic: product-events, Group: ml-pipeline. "
            "Partitions: [0,1,2,3] all behind"
        )
        print(f"  wrote Kafka lag warning {i + 1}/{repeat}")
        time.sleep(0.3)


# ── Scenario 4: Generic error rate spike ─────────────────────────────────────
# Triggers rule: "Error rate spike" (threshold=20, window=300s)
# Maps to RAG chunks: general error runbooks
def scenario_error_spike(repeat: int = 22) -> None:
    print(f"\n[Scenario 4] Firing generic errors × {repeat} (simulates error rate spike)")
    errors = [
        "Unhandled exception in request handler: NullPointerException at line 142",
        "Failed to process request: Connection refused to upstream service",
        "Request timeout after 5000ms — circuit breaker threshold approaching",
        "Internal server error: database query exceeded 30s limit",
        "Memory allocation failed: heap fragmentation detected",
    ]
    import itertools
    for i, msg in zip(range(repeat), itertools.cycle(errors)):
        log.error(f"sample-app - {msg}")
        print(f"  wrote error {i + 1}/{repeat}")
        time.sleep(0.2)


# ── Scenario 5: Redis connection failure ─────────────────────────────────────
# Triggers via error rate spike rule
def scenario_redis_failure(repeat: int = 5) -> None:
    print(f"\n[Scenario 5] Firing Redis connection errors × {repeat}")
    for i in range(repeat):
        log.error(
            "celery-worker - redis.exceptions.ConnectionError: "
            "Error 111 connecting to localhost:6379. Connection refused. "
            "Task catalog.tasks.reindex_products[abc-123] failed"
        )
        print(f"  wrote Redis error {i + 1}/{repeat}")
        time.sleep(0.4)


SCENARIOS = {
    1: ("CUDA OOM (ml-inference)",          scenario_cuda_oom),
    2: ("DB connection pool exhausted",      scenario_db_exhaustion),
    3: ("Kafka consumer lag",                scenario_kafka_lag),
    4: ("Generic error rate spike",          scenario_error_spike),
    5: ("Redis connection failure",          scenario_redis_failure),
}


def menu() -> None:
    print("\n" + "=" * 55)
    print("  Agentic Framework — Error Trigger")
    print("  Writes errors to: sample_app/logs/app.log")
    print("=" * 55)
    print("\nScenarios (each triggers a different anomaly rule):\n")
    for k, (label, _) in SCENARIOS.items():
        print(f"  {k}. {label}")
    print("  0. Quit\n")

    while True:
        choice = input("Pick scenario (0-5): ").strip()
        if choice == "0":
            print("Bye.")
            sys.exit(0)
        if choice.isdigit() and int(choice) in SCENARIOS:
            label, fn = SCENARIOS[int(choice)]
            print(f"\nRunning: {label}")
            print("Watch uvicorn terminal + dashboard at http://localhost:8501\n")
            fn()
            print(f"\nDone. Incident should appear in dashboard within 5-10 seconds.")
            print("Check: http://localhost:8501 → Overview tab")
            break
        print("  Invalid choice, try again.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=int, choices=SCENARIOS.keys(),
                        help="Run a specific scenario directly")
    args = parser.parse_args()

    if args.scenario:
        label, fn = SCENARIOS[args.scenario]
        print(f"Running scenario {args.scenario}: {label}")
        fn()
        print("Done.")
    else:
        menu()


if __name__ == "__main__":
    main()
