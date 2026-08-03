from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx


def main() -> None:
    incident_path = Path(sys.argv[1] if len(sys.argv) > 1 else "sample_data/incidents/checkout_latency.json")
    payload = json.loads(incident_path.read_text(encoding="utf-8"))
    response = httpx.post("http://localhost:8000/incidents/trigger", json=payload, timeout=30)
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()

