from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from core.config.settings import Settings
from models import IncidentState


class IncidentStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._table = None
        if settings.use_aws:
            import boto3

            self._table = boto3.resource("dynamodb", region_name=settings.aws_region).Table(
                settings.dynamodb_incidents_table
            )

    def exists(self, incident_id: str) -> bool:
        return self.get(incident_id) is not None

    def get(self, incident_id: str) -> IncidentState | None:
        if self._table:
            item = self._table.get_item(Key={"incident_id": incident_id}).get("Item")
            return IncidentState.model_validate(item) if item else None
        return self._load_local().get(incident_id)

    def list(self) -> list[IncidentState]:
        if self._table:
            items = self._table.scan(Limit=100).get("Items", [])
            return [IncidentState.model_validate(item) for item in items]
        return sorted(self._load_local().values(), key=lambda item: item.created_at, reverse=True)

    def save(self, state: IncidentState) -> IncidentState:
        state.touch()
        if self._table:
            self._table.put_item(Item=json.loads(state.model_dump_json(), parse_float=Decimal))
            return state
        data = self._load_raw_local()
        data[state.incident_id] = json.loads(state.model_dump_json())
        path = Path(self.settings.local_store_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return state

    def _load_local(self) -> dict[str, IncidentState]:
        return {
            key: IncidentState.model_validate(value)
            for key, value in self._load_raw_local().items()
        }

    def _load_raw_local(self) -> dict[str, Any]:
        path = Path(self.settings.local_store_path)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
