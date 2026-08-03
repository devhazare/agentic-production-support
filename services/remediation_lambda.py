from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from services.mock_integrations import SUPPORTED_ACTIONS


def handler(event: dict[str, Any], context: object | None = None) -> dict[str, Any]:
    incident_id = event.get("incident_id", "unknown")
    action = event.get("action", "none")
    dry_run = bool(event.get("dry_run", True))
    if action not in SUPPORTED_ACTIONS:
        return {
            "incident_id": incident_id,
            "action": action,
            "status": "skipped",
            "dry_run": dry_run,
            "message": "Unsupported mock remediation action.",
        }
    return {
        "incident_id": incident_id,
        "action": action,
        "status": "success",
        "dry_run": dry_run,
        "message": f"Mock remediation accepted for {action}; no production resources changed.",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

