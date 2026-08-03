from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from core.config.settings import Settings
from models import AuditLog


class AuditService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._ddb = None
        if settings.use_aws:
            import boto3

            self._ddb = boto3.resource("dynamodb", region_name=settings.aws_region).Table(
                settings.dynamodb_audit_table
            )

    def record(self, event_type: str, incident_id: str | None = None, **details: object) -> AuditLog:
        entry = AuditLog(
            audit_id=str(uuid4()),
            incident_id=incident_id,
            event_type=event_type,
            details=dict(details),
        )
        if self._ddb:
            self._ddb.put_item(Item=json.loads(entry.model_dump_json(), parse_float=Decimal))
        else:
            path = Path(self.settings.local_audit_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(entry.model_dump_json() + "\n")
        return entry
