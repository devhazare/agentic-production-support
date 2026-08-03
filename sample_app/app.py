"""
sample_app/app.py
-----------------
A simple Python app that logs normally.
The framework watches this app's log file and creates incidents when errors appear.

Run:  python sample_app/app.py
Logs: sample_app/logs/app.log
"""

from __future__ import annotations

import logging
import time
import random
from pathlib import Path

# ── Logger setup — format must match PythonLogParser regex ───────────────────
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

SERVICES = ["order-service", "payment-service", "user-service", "inventory-service"]


def process_order(order_id: int) -> None:
    svc = random.choice(SERVICES)
    log.info(f"Processing order {order_id} on {svc}")
    time.sleep(0.1)
    log.info(f"Order {order_id} completed successfully. service={svc}")


def main() -> None:
    log.info("sample-app started. Logging to sample_app/logs/app.log")
    log.info("Run trigger_error.py in another terminal to create an incident.")
    counter = 0
    while True:
        counter += 1
        process_order(random.randint(10000, 99999))
        time.sleep(2)


if __name__ == "__main__":
    main()
