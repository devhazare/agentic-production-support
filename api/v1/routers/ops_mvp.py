from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.config.settings import Settings, get_settings
from models import IncidentEvent, IncidentState
from orchestration.langgraph_workflow import IncidentWorkflow
from services.audit_log import AuditService
from services.aws_knowledge import KnowledgeService
from services.ops_store import IncidentStore

router = APIRouter(tags=["ai-ops-mvp"])


class ApprovalBody(BaseModel):
    approver: str
    comment: str = ""


class KnowledgeUploadBody(BaseModel):
    title: str
    text: str
    doc_type: str = "runbook"


def _workflow(settings: Settings) -> IncidentWorkflow:
    return IncidentWorkflow(IncidentStore(settings))


@router.get("/health")
async def mvp_health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return {
        "status": "ok",
        "service": "AI Operational Intelligence MVP",
        "use_aws": settings.use_aws,
        "aws_region": settings.aws_region,
    }


@router.post("/incidents/trigger", response_model=IncidentState)
async def trigger_incident(
    event: IncidentEvent,
    settings: Settings = Depends(get_settings),
) -> IncidentState:
    return _workflow(settings).run(event)


@router.get("/incidents/{incident_id}", response_model=IncidentState)
async def get_incident(
    incident_id: str,
    settings: Settings = Depends(get_settings),
) -> IncidentState:
    state = IncidentStore(settings).get(incident_id)
    if not state:
        raise HTTPException(status_code=404, detail="Incident not found")
    return state


@router.get("/incidents", response_model=list[IncidentState])
async def list_incidents(settings: Settings = Depends(get_settings)) -> list[IncidentState]:
    return IncidentStore(settings).list()


@router.post("/incidents/{incident_id}/approve", response_model=IncidentState)
async def approve_incident(
    incident_id: str,
    body: ApprovalBody,
    settings: Settings = Depends(get_settings),
) -> IncidentState:
    try:
        return _workflow(settings).approve(incident_id, body.approver, body.comment)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/incidents/{incident_id}/reject", response_model=IncidentState)
async def reject_incident(
    incident_id: str,
    body: ApprovalBody,
    settings: Settings = Depends(get_settings),
) -> IncidentState:
    try:
        return _workflow(settings).reject(incident_id, body.approver, body.comment)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/incidents/{incident_id}/needs-more-info", response_model=IncidentState)
async def needs_more_info(
    incident_id: str,
    body: ApprovalBody,
    settings: Settings = Depends(get_settings),
) -> IncidentState:
    try:
        return _workflow(settings).needs_more_info(incident_id, body.approver, body.comment)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/knowledge/upload")
async def upload_knowledge(
    body: KnowledgeUploadBody,
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    doc = KnowledgeService(settings).upload_text(body.title, body.text, body.doc_type)
    AuditService(settings).record("knowledge_uploaded", details=doc.model_dump())
    return {"document": doc}


@router.post("/knowledge/reindex")
async def reindex_knowledge(settings: Settings = Depends(get_settings)) -> dict[str, int]:
    return {"indexed": KnowledgeService(settings).index_documents()}


def lambda_handler(event: dict, context: object | None = None) -> dict[str, object]:
    settings = get_settings()
    incident = IncidentEvent.model_validate(event.get("detail", event))
    state = _workflow(settings).run(incident)
    return {"statusCode": 200, "body": state.model_dump()}
