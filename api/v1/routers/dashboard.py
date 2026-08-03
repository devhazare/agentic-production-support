"""
api/v1/routers/dashboard.py
---------------------------
Runtime dashboard API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from core.config.settings import Settings, get_settings
from services.incident_store import IncidentStore
from services.observability import get_observability
from services.ops_store import IncidentStore as OpsIncidentStore

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

LANGGRAPH_NODES = [
    "incident_agent",
    "retrieval_agent",
    "rca_agent",
    "decision_agent",
    "approval_agent",
    "mock_remediation_agent",
    "communication_agent",
    "learning_agent",
]

LANGGRAPH_EDGES = [
    {"from": "incident_agent", "to": "retrieval_agent", "condition": "not duplicate/error"},
    {"from": "incident_agent", "to": "learning_agent", "condition": "duplicate or error"},
    {"from": "retrieval_agent", "to": "rca_agent", "condition": "always"},
    {"from": "rca_agent", "to": "decision_agent", "condition": "always"},
    {"from": "decision_agent", "to": "approval_agent", "condition": "human_review or remediation policy"},
    {"from": "approval_agent", "to": "communication_agent", "condition": "awaiting approval"},
    {"from": "approval_agent", "to": "mock_remediation_agent", "condition": "approval not required"},
    {"from": "mock_remediation_agent", "to": "communication_agent", "condition": "always"},
    {"from": "communication_agent", "to": "learning_agent", "condition": "always"},
]


def _rag_status(settings: Settings) -> dict[str, Any]:
    base = Path(str(settings.faiss_index_path))
    index_path = Path(str(base) + ".index")
    meta_path = Path(str(base) + "_meta.pkl")
    embedder_path = Path(str(base) + "_embedder.pkl")
    kb_path = Path(settings.knowledge_base_path)
    kb_files = list(kb_path.glob("*")) if kb_path.exists() else []
    return {
        "status": "ready" if index_path.exists() and meta_path.exists() else "not_ready",
        "vector_store": settings.vector_store.value,
        "knowledge_base_path": str(kb_path),
        "knowledge_files": len([p for p in kb_files if p.is_file()]),
        "index_exists": index_path.exists(),
        "metadata_exists": meta_path.exists(),
        "embedder_exists": embedder_path.exists(),
    }


def _ops_incident_row(state: Any) -> dict[str, Any]:
    event = state.event
    approval_status = state.approval.status.value if state.approval else None
    confidence = state.rca.confidence_score if state.rca else None
    return {
        "source": "mvp",
        "incident_id": state.incident_id,
        "service": event.service_name if event else "unknown",
        "severity": event.severity.value if event else "unknown",
        "status": state.status,
        "stage": state.status,
        "decision": state.decision.route if state.decision else None,
        "approval_status": approval_status,
        "validation": None,
        "updated": state.updated_at,
        "confidence": confidence,
        "rca_summary": state.rca_summary,
    }


def _ops_agent_activity(states: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for state in states:
        for index, step in enumerate(state.decision_path):
            agent = step.split(":", 1)[0]
            rows.append(
                {
                    "time": state.updated_at,
                    "timestamp": state.updated_at,
                    "incident_id": state.incident_id,
                    "agent": agent,
                    "status": "completed" if state.status != "error" else "failed",
                    "duration_ms": None,
                    "error": state.error if state.status == "error" else None,
                    "sequence": index,
                    "detail": step,
                    "source": "mvp",
                }
            )
    return list(reversed(rows))


@router.get(
    "/status",
    summary="Return runtime dashboard telemetry",
)
async def dashboard_status(
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    registry = get_observability()
    data = registry.snapshot(settings)
    data["rag"] = _rag_status(settings)

    store = IncidentStore(settings)
    mongo_incidents = await store.list_recent(limit=25)
    data["mongodb"] = {
        "enabled": settings.mongodb_enabled,
        "connected": store.enabled,
        "database": settings.mongodb_database,
        "collection": settings.mongodb_incidents_collection,
        "recent_incidents": mongo_incidents,
    }

    ops_store = OpsIncidentStore(settings)
    ops_states = ops_store.list()
    ops_rows = [_ops_incident_row(state) for state in ops_states]
    data["ops_mvp"] = {
        "incident_count": len(ops_rows),
        "recent_incidents": ops_rows,
    }
    data["langgraph"] = {
        "nodes": LANGGRAPH_NODES,
        "edges": LANGGRAPH_EDGES,
        "recent_paths": [
            {
                "incident_id": state.incident_id,
                "status": state.status,
                "decision_path": state.decision_path,
            }
            for state in ops_states[:10]
        ],
    }
    data["incidents"] = ops_rows + data.get("incidents", [])
    data["agent_activity"] = _ops_agent_activity(ops_states) + data.get("agent_activity", [])
    data["metrics"]["incidents_total"] = data["metrics"].get("incidents_total", 0) + len(ops_rows)
    data["metrics"]["incidents_open"] = data["metrics"].get("incidents_open", 0) + sum(
        1 for row in ops_rows if row.get("status") not in {"remediated", "rejected", "duplicate"}
    )
    data["metrics"]["human_approval"] = data["metrics"].get("human_approval", 0) + sum(
        1 for row in ops_rows if row.get("approval_status") == "pending"
    )
    return data
