#!/usr/bin/env python3
"""Generate Magento fixed-issue knowledge base seed data.

Outputs:
  data/knowledge_base/issues.psv
  data/knowledge_base/fixed_issues.md

The raw PSV header intentionally matches the user-provided format:
Issueid|type|bugis|descpt|priority|seviorty|start_datetime|enddatatime|RCA|fixedby
"""

from __future__ import annotations

import argparse
import random
import re
from datetime import datetime, timedelta
from pathlib import Path


HEADER = "Issueid|type|bugis|descpt|priority|seviorty|start_datetime|enddatatime|RCA|fixedby"

BUGS = [
    {
        "bugis": "checkout_db_lock_timeout",
        "area": "checkout",
        "symptom": "checkout save order failed with database lock timeout",
        "rca": "Concurrent checkout requests locked quote and sales_order rows during payment placement",
        "fixes": [
            "Reduced transaction scope in checkout save order flow",
            "Added retry with backoff for transient InnoDB lock timeouts",
            "Moved inventory reservation update outside the payment transaction",
        ],
    },
    {
        "bugis": "payment_gateway_timeout",
        "area": "payment",
        "symptom": "payment authorization intermittently timed out",
        "rca": "Payment gateway latency exceeded Magento client timeout during peak traffic",
        "fixes": [
            "Increased gateway timeout from 10s to 30s",
            "Added idempotency key and retry for authorization calls",
            "Routed failed gateway calls to secondary provider after timeout threshold",
        ],
    },
    {
        "bugis": "cart_missing_entity",
        "area": "cart",
        "symptom": "customer cart lookup returned no such entity",
        "rca": "Expired quote records were removed while frontend sections still referenced stale cart ids",
        "fixes": [
            "Cleared stale customer section data after quote expiration",
            "Added fallback to create a fresh quote when cart id is missing",
            "Reduced frontend local storage TTL for cart metadata",
        ],
    },
    {
        "bugis": "catalog_reindex_memory_limit",
        "area": "catalog",
        "symptom": "catalog reindex hit PHP memory limit",
        "rca": "Full catalog reindex loaded too many product ids into memory in one batch",
        "fixes": [
            "Changed catalog reindex batch size from 50000 to 5000",
            "Raised memory limit only for the cron PHP pool",
            "Added progress checkpointing to resume failed reindex jobs",
        ],
    },
    {
        "bugis": "redis_session_pool_pressure",
        "area": "session",
        "symptom": "Redis connection pool approached capacity and slowed customer sessions",
        "rca": "Session lock waits accumulated because Redis pool size was lower than concurrent PHP workers",
        "fixes": [
            "Increased Redis maxclients and PHP session pool size",
            "Reduced session lock timeout for frontend requests",
            "Moved anonymous customer sections to cache-backed storage",
        ],
    },
    {
        "bugis": "full_page_cache_stale",
        "area": "cache",
        "symptom": "customers saw stale product price after promotion update",
        "rca": "Full page cache tags were not invalidated for promotion price rules",
        "fixes": [
            "Added price rule cache tag invalidation on promotion save",
            "Purged affected Varnish objects after catalog rule apply",
            "Added integration test for promotion price cache refresh",
        ],
    },
    {
        "bugis": "admin_product_save_500",
        "area": "admin",
        "symptom": "admin product save returned HTTP 500",
        "rca": "Custom product attribute observer raised validation error after schema change",
        "fixes": [
            "Updated observer to handle null custom attribute values",
            "Backfilled missing custom attribute defaults",
            "Added admin product save regression test",
        ],
    },
    {
        "bugis": "cron_schedule_missed",
        "area": "cron",
        "symptom": "Magento cron jobs missed scheduled execution windows",
        "rca": "Long-running catalog jobs blocked the default cron group",
        "fixes": [
            "Moved heavy catalog jobs to a dedicated cron group",
            "Added max runtime alert for cron schedule lag",
            "Split sales cleanup job into smaller chunks",
        ],
    },
]

PRIORITIES = ["P0", "P1", "P2", "P3"]
SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
FIXERS = [
    "sre-oncall",
    "magento-platform-team",
    "checkout-team",
    "payments-team",
    "catalog-team",
    "infra-team",
    "database-team",
    "release-engineering",
]


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]


def sanitize(value: str) -> str:
    return " ".join(value.replace("|", "/").split())


def choose_priority_severity(rng: random.Random, bug: dict[str, object]) -> tuple[str, str]:
    bugis = str(bug["bugis"])
    if "timeout" in bugis or "500" in bugis:
        priority_weights = [10, 45, 35, 10]
        severity_weights = [8, 45, 35, 12]
    elif "memory" in bugis or "db_lock" in bugis:
        priority_weights = [15, 50, 25, 10]
        severity_weights = [12, 48, 30, 10]
    else:
        priority_weights = [3, 22, 50, 25]
        severity_weights = [2, 20, 48, 30]
    return (
        rng.choices(PRIORITIES, weights=priority_weights, k=1)[0],
        rng.choices(SEVERITIES, weights=severity_weights, k=1)[0],
    )


def parse_status(access_line: str) -> str:
    match = re.search(r'" [1-5][0-9][0-9] ', access_line)
    return match.group(0).strip().strip('"') if match else "unknown"


def build_issue(
    issue_number: int,
    rng: random.Random,
    access_lines: list[str],
    exception_lines: list[str],
    system_lines: list[str],
    base_time: datetime,
) -> dict[str, str]:
    bug = rng.choice(BUGS)
    priority, severity = choose_priority_severity(rng, bug)
    start = base_time + timedelta(minutes=issue_number * 7 + rng.randint(0, 4))
    duration = rng.randint(6, 180)
    if severity == "CRITICAL":
        duration = rng.randint(12, 240)
    elif severity == "LOW":
        duration = rng.randint(3, 45)
    end = start + timedelta(minutes=duration)

    access = rng.choice(access_lines) if access_lines else "no access log sample available"
    exception = rng.choice(exception_lines) if exception_lines else "no exception log sample available"
    system = rng.choice(system_lines) if system_lines else "no system log sample available"
    status = parse_status(access)
    fix = rng.choice(bug["fixes"])  # type: ignore[index]
    fixedby = rng.choice(FIXERS)

    impact_count = rng.randint(3, 1800)
    store = rng.choice(["default", "us_en", "eu_en", "in_en", "b2b"])
    desc = (
        f"Magento {bug['area']} issue in store {store}: {bug['symptom']}; "
        f"observed HTTP status {status}; impacted requests approx {impact_count}; "
        f"access evidence: {access}; exception evidence: {exception}; system evidence: {system}"
    )
    rca = (
        f"{bug['rca']}. Correlated access, exception, and system logs showed matching timestamps. "
        f"Primary fix: {fix}."
    )

    return {
        "Issueid": f"MAG-{issue_number:05d}",
        "type": "magento",
        "bugis": str(bug["bugis"]),
        "descpt": sanitize(desc),
        "priority": priority,
        "seviorty": severity,
        "start_datetime": start.strftime("%Y-%m-%d %H:%M:%S"),
        "enddatatime": end.strftime("%Y-%m-%d %H:%M:%S"),
        "RCA": sanitize(rca),
        "fixedby": fixedby,
    }


def write_outputs(rows: list[dict[str, str]], psv_path: Path, md_path: Path) -> None:
    psv_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    with psv_path.open("w", encoding="utf-8", newline="\n") as psv:
        psv.write(HEADER + "\n")
        for row in rows:
            psv.write(
                "|".join(
                    [
                        row["Issueid"],
                        row["type"],
                        row["bugis"],
                        row["descpt"],
                        row["priority"],
                        row["seviorty"],
                        row["start_datetime"],
                        row["enddatatime"],
                        row["RCA"],
                        row["fixedby"],
                    ]
                )
                + "\n"
            )

    with md_path.open("w", encoding="utf-8", newline="\n") as md:
        md.write("# Magento Fixed Issue Knowledge Base\n\n")
        md.write(
            "This file contains generated Magento fixed issue history for RAG retrieval. "
            "Each issue references sampled access.log, exception.log, and system.log evidence.\n\n"
        )
        for row in rows:
            md.write(f"## Issue {row['Issueid']}\n\n")
            md.write(f"- Type: {row['type']}\n")
            md.write(f"- Bug Is: {row['bugis']}\n")
            md.write(f"- Description: {row['descpt']}\n")
            md.write(f"- Priority: {row['priority']}\n")
            md.write(f"- Severity: {row['seviorty']}\n")
            md.write(f"- Start Datetime: {row['start_datetime']}\n")
            md.write(f"- End Datetime: {row['enddatatime']}\n")
            md.write(f"- RCA: {row['RCA']}\n")
            md.write(f"- Fixed By: {row['fixedby']}\n\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=30000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--logs-dir", type=Path, default=Path("./sample_logs/magento"))
    parser.add_argument("--psv", type=Path, default=Path("./data/knowledge_base/issues.psv"))
    parser.add_argument("--md", type=Path, default=Path("./data/knowledge_base/fixed_issues.md"))
    args = parser.parse_args()

    if args.count <= 0:
        raise SystemExit("--count must be positive")

    rng = random.Random(args.seed)
    access_lines = read_lines(args.logs_dir / "access.log")
    exception_lines = read_lines(args.logs_dir / "exception.log")
    system_lines = read_lines(args.logs_dir / "system.log")
    base_time = datetime(2026, 1, 1, 0, 0, 0)

    rows = [
        build_issue(i, rng, access_lines, exception_lines, system_lines, base_time)
        for i in range(1, args.count + 1)
    ]
    write_outputs(rows, args.psv, args.md)

    print(f"Generated {args.count} Magento fixed issues")
    print(f"PSV: {args.psv}")
    print(f"Markdown: {args.md}")
    print(f"Access log samples used: {len(access_lines)}")
    print(f"Exception log samples used: {len(exception_lines)}")
    print(f"System log samples used: {len(system_lines)}")


if __name__ == "__main__":
    main()
