"""
services/incident_store/__init__.py
-----------------------------------
Incident persistence adapters.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from core.config.settings import Settings
from core.logging import get_logger
from models import PipelineResult

logger = get_logger(__name__)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    return value


class IncidentStore:
    """Stores completed incident pipeline results in MongoDB when available."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._collection: Any | None = None
        self._enabled = False

        if not settings.mongodb_enabled:
            logger.info("incident_store.disabled_by_config")
            return

        try:
            from pymongo import MongoClient  # noqa: PLC0415

            client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=1500)
            client.admin.command("ping")
            db = client[settings.mongodb_database]
            self._collection = db[settings.mongodb_incidents_collection]
            self._collection.create_index("incident_id", unique=True)
            self._collection.create_index("created_at")
            self._collection.create_index("service")
            self._collection.create_index("decision")
            self._enabled = True
            logger.info(
                "incident_store.mongodb_ready",
                database=settings.mongodb_database,
                collection=settings.mongodb_incidents_collection,
            )
        except ModuleNotFoundError:
            logger.warning("incident_store.pymongo_missing", install="pip install pymongo")
        except Exception as exc:
            logger.warning("incident_store.mongodb_unavailable", error=str(exc))

    @property
    def enabled(self) -> bool:
        return self._enabled and self._collection is not None

    async def save_pipeline_result(
        self,
        result: PipelineResult,
        trigger: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return

        document = self._build_document(result, trigger or {})
        await asyncio.to_thread(self._upsert, document)

    async def create_detected_incident(
        self,
        *,
        incident_id: str,
        service: str,
        alert_type: str,
        log_source: str,
        logs_snippet: str,
        metrics: dict[str, Any],
        trigger: dict[str, Any],
    ) -> None:
        if not self.enabled:
            return

        now = datetime.now(timezone.utc).isoformat()
        document = {
            "incident_id": incident_id,
            "created_at": now,
            "updated_at": now,
            "source": "log_monitor",
            "service": service,
            "alert_type": alert_type,
            "severity": None,
            "status": "OPEN",
            "log_source": log_source,
            "logs_snippet": logs_snippet,
            "metrics": _jsonable(metrics),
            "trigger": _jsonable(trigger),
            "lifecycle_stage": "DETECTED",
            "rca": None,
            "decision": None,
            "decision_result": None,
            "remediation_plan": None,
            "validation": None,
            "communication": None,
            "approval_status": "NOT_REQUIRED",
            "approval": None,
            "remediation_executed": False,
            "human_approval_needed": False,
            "pipeline_duration_ms": None,
            "error": None,
        }
        await asyncio.to_thread(self._insert_initial, document)

    async def list_recent(self, limit: int = 25) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        return await asyncio.to_thread(self._list_recent, limit)

    async def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        return await asyncio.to_thread(self._get_incident, incident_id)

    async def update_incident_fields(
        self, incident_id: str, fields: dict[str, Any]
    ) -> None:
        if not self.enabled:
            return
        await asyncio.to_thread(self._update_incident_fields, incident_id, fields)

    def _insert_initial(self, document: dict[str, Any]) -> None:
        assert self._collection is not None
        self._collection.update_one(
            {"incident_id": document["incident_id"]},
            {"$setOnInsert": document},
            upsert=True,
        )

    def _upsert(self, document: dict[str, Any]) -> None:
        assert self._collection is not None
        created_at = document["created_at"]
        set_document = {k: v for k, v in document.items() if k != "created_at"}
        self._collection.update_one(
            {"incident_id": document["incident_id"]},
            {"$set": set_document, "$setOnInsert": {"created_at": created_at}},
            upsert=True,
        )

    def _list_recent(self, limit: int) -> list[dict[str, Any]]:
        assert self._collection is not None
        cursor = (
            self._collection.find({}, {"_id": 0})
            .sort("updated_at", -1)
            .limit(max(1, min(limit, 100)))
        )
        return list(cursor)

    def _get_incident(self, incident_id: str) -> dict[str, Any] | None:
        assert self._collection is not None
        return self._collection.find_one({"incident_id": incident_id}, {"_id": 0})

    def _update_incident_fields(
        self, incident_id: str, fields: dict[str, Any]
    ) -> None:
        assert self._collection is not None
        payload = _jsonable(fields)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._collection.update_one(
            {"incident_id": incident_id},
            {"$set": payload},
            upsert=False,
        )

    @staticmethod
    def _build_document(
        result: PipelineResult,
        trigger: dict[str, Any],
    ) -> dict[str, Any]:
        incident = result.incident
        decision = result.decision
        rca = result.rca
        plan = result.remediation_plan
        validation = result.validation
        communication = result.communication
        now = datetime.now(timezone.utc).isoformat()

        return {
            "incident_id": incident.incident_id,
            "created_at": now,
            "updated_at": now,
            "source": "log_monitor",
            "service": incident.service,
            "alert_type": incident.alert_type,
            "severity": incident.severity.value,
            "status": incident.status.value,
            "log_source": incident.log_source.value if incident.log_source else None,
            "logs_snippet": incident.logs_snippet,
            "metrics": _jsonable(incident.metrics),
            "trigger": _jsonable(trigger),
            "lifecycle_stage": "PIPELINE_COMPLETED",
            "rca": _jsonable(rca),
            "decision": decision.decision.value if decision else None,
            "decision_result": _jsonable(decision),
            "remediation_plan": _jsonable(plan),
            "validation": _jsonable(validation),
            "communication": _jsonable(communication),
            "approval_status": "PENDING_APPROVAL" if result.human_approval_needed else "NOT_REQUIRED",
            "approval": None,
            "remediation_executed": result.remediation_executed,
            "human_approval_needed": result.human_approval_needed,
            "pipeline_duration_ms": result.pipeline_duration_ms,
            "error": result.error,
            "pipeline_result": _jsonable(result),
        }
