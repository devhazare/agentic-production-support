"""
api/v1/routers/incidents.py
----------------------------
Incident analysis endpoints.

API contract:
  POST /api/v1/incidents/analyze   — run full pipeline on alert payload
  POST /api/v1/incidents/mock      — trigger a random mock incident
  GET  /api/v1/incidents/{id}      — get incident by ID (stub)
  GET  /api/v1/incidents/history   — list past incidents
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from core.config.settings import Settings, get_settings
from core.exceptions import BaseFrameworkError
from core.logging import get_logger
from models import (
    AlertPayloadSchema,
    ApprovalRequestSchema,
    ApprovalResponseSchema,
    CommunicationResult,
    ContextChunk,
    Decision,
    DecisionResult,
    Incident,
    IncidentStatus,
    LogSource,
    Metrics,
    PipelineResult,
    PipelineResultSchema,
    RCAResult,
    RemediationPlan,
    RemediationStep,
    Severity,
    StepStatus,
)
from orchestration import Orchestrator, OrchestratorBuilder
from services.incident_store import IncidentStore

logger = get_logger(__name__)

router = APIRouter(prefix="/incidents", tags=["incidents"])

_orchestrator: Orchestrator | None = None


def _get_orchestrator(settings: Settings = Depends(get_settings)) -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = OrchestratorBuilder().with_settings(settings).build()
    return _orchestrator


def _to_schema(result: object) -> PipelineResultSchema:
    r: PipelineResult = result  # type: ignore[assignment]
    return PipelineResultSchema(
        incident_id=r.incident.incident_id,
        service=r.incident.service,
        severity=r.incident.severity.value,
        status=r.incident.status.value,
        decision=r.decision.decision.value if r.decision else None,
        risk_score=r.decision.risk_score if r.decision else None,
        rca_summary=r.rca.rca_text[:500] if r.rca else None,
        remediation_steps=len(r.remediation_plan.steps) if r.remediation_plan else 0,
        estimated_mttr_minutes=r.remediation_plan.estimated_mttr_minutes if r.remediation_plan else 0,
        human_approval_needed=r.human_approval_needed,
        validation_status=r.validation.status if r.validation else None,
        validation_passed=r.validation.passed if r.validation else None,
        communication_channels=r.communication.channels if r.communication else [],
        pipeline_duration_ms=r.pipeline_duration_ms,
        error=r.error,
    )


def _store(settings: Settings) -> IncidentStore:
    return IncidentStore(settings)


def _rehydrate_incident(document: dict) -> Incident:
    metrics = document.get("metrics") or {}
    raw_payload = document.get("pipeline_result", {}).get("incident", {}).get("raw_payload") or {}
    log_source = document.get("log_source")
    return Incident(
        incident_id=document["incident_id"],
        service=document.get("service") or "unknown",
        alert_type=document.get("alert_type") or "Unknown",
        severity=Severity(document.get("severity") or "HIGH"),
        status=IncidentStatus(document.get("status") or "ESCALATED"),
        metrics=Metrics(
            cpu_percent=float(metrics.get("cpu_percent", 0.0)),
            memory_mb=float(metrics.get("memory_mb", 0.0)),
            error_rate=float(metrics.get("error_rate", 0.0)),
            latency_p99_ms=float(metrics.get("latency_p99_ms", 0.0)),
            db_connections=int(metrics.get("db_connections", 0)),
            db_max_connections=int(metrics.get("db_max_connections", 100)),
        ),
        logs_snippet=document.get("logs_snippet") or "",
        log_source=LogSource(log_source) if log_source else None,
        raw_payload=raw_payload,
    )


def _rehydrate_rca(document: dict) -> RCAResult:
    rca = document.get("rca") or {}
    chunks = [
        ContextChunk(
            text=chunk.get("text", ""),
            source=chunk.get("source", "unknown"),
            chunk_id=chunk.get("chunk_id", ""),
            score=float(chunk.get("score", 0.0)),
        )
        for chunk in rca.get("context_chunks", [])
        if isinstance(chunk, dict)
    ]
    return RCAResult(
        incident_id=document["incident_id"],
        rca_text=rca.get("rca_text") or "",
        confidence=rca.get("confidence") or "MEDIUM",
        context_chunks=chunks,
        timestamp=rca.get("timestamp") or "",
    )


def _rehydrate_plan(document: dict) -> RemediationPlan:
    plan = document.get("remediation_plan") or {}
    steps = []
    for raw_step in plan.get("steps", []):
        if not isinstance(raw_step, dict):
            continue
        steps.append(
            RemediationStep(
                step_number=int(raw_step.get("step_number", len(steps) + 1)),
                action_type=raw_step.get("action_type", "INVESTIGATE"),
                description=raw_step.get("description", ""),
                status=StepStatus(raw_step.get("status", "PENDING")),
                duration_ms=int(raw_step.get("duration_ms", 0)),
                error=raw_step.get("error", ""),
            )
        )
    return RemediationPlan(
        incident_id=document["incident_id"],
        steps=steps,
        llm_plan_text=plan.get("llm_plan_text") or "",
        estimated_mttr_minutes=int(plan.get("estimated_mttr_minutes", 0)),
        executed=bool(plan.get("executed", False)),
    )


@router.post(
    "/analyze",
    response_model=PipelineResultSchema,
    status_code=status.HTTP_200_OK,
    summary="Analyze an alert and run the full agent pipeline",
    description=(
        "Accepts a raw alert payload (from CloudWatch, Prometheus, or a log monitor), "
        "runs it through Detection → RCA → Decision → Remediation → Validation → "
        "Communication agents, and returns a structured result."
    ),
)
async def analyze_alert(
    payload: AlertPayloadSchema,
    settings: Settings = Depends(get_settings),
    orchestrator: Orchestrator = Depends(_get_orchestrator),
) -> PipelineResultSchema:
    try:
        result = await orchestrator.run(payload)
        await _store(settings).save_pipeline_result(
            result,
            trigger={"source": "api.incidents.analyze", "payload": payload.model_dump()},
        )
        return _to_schema(result)
    except BaseFrameworkError as exc:
        logger.error("api.analyze.error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": exc.message, "context": exc.context},
        ) from exc


@router.post(
    "/mock",
    response_model=PipelineResultSchema,
    status_code=status.HTTP_200_OK,
    summary="Trigger a random mock incident",
)
async def analyze_mock(
    settings: Settings = Depends(get_settings),
    orchestrator: Orchestrator = Depends(_get_orchestrator),
) -> PipelineResultSchema:
    from agents.detection import _MOCK_INCIDENTS, generate_mock_incident  # noqa: PLC0415
    mock_dict = generate_mock_incident()
    payload = AlertPayloadSchema(**mock_dict)
    try:
        result = await orchestrator.run(payload)
        await _store(settings).save_pipeline_result(
            result,
            trigger={"source": "api.incidents.mock", "payload": payload.model_dump()},
        )
        return _to_schema(result)
    except BaseFrameworkError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": exc.message},
        ) from exc


@router.post(
    "/{incident_id}/approve",
    response_model=ApprovalResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Approve a human-in-the-loop remediation plan",
)
async def approve_incident(
    incident_id: str,
    approval: ApprovalRequestSchema,
    settings: Settings = Depends(get_settings),
) -> ApprovalResponseSchema:
    store = _store(settings)
    document = await store.get_incident(incident_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Incident not found: {incident_id}")

    if document.get("decision") != Decision.HUMAN_APPROVAL.value:
        raise HTTPException(
            status_code=409,
            detail="Incident is not waiting for human approval",
        )
    if document.get("approval_status") == "APPROVED":
        raise HTTPException(status_code=409, detail="Incident is already approved")
    if document.get("approval_status") == "REJECTED":
        raise HTTPException(status_code=409, detail="Incident was rejected")
    if not document.get("remediation_plan"):
        raise HTTPException(status_code=409, detail="No remediation plan is available")

    from agents.base import AgentContext  # noqa: PLC0415
    from agents.communication import CommunicationAgent, CommunicationInput  # noqa: PLC0415
    from agents.remediation import execute_remediation_plan  # noqa: PLC0415
    from agents.validation import ValidationAgent, ValidationInput  # noqa: PLC0415
    from services.observability import get_observability  # noqa: PLC0415

    incident = _rehydrate_incident(document)
    rca = _rehydrate_rca(document)
    plan = _rehydrate_plan(document)
    approved_decision = DecisionResult(
        incident_id=incident.incident_id,
        decision=Decision.AUTO_REMEDIATE,
        reason=f"Human approved by {approval.approved_by}",
        risk_score=float((document.get("decision_result") or {}).get("risk_score", 1.0)),
    )
    context = AgentContext(incident_id=f"approval-{incident.incident_id}")

    await store.update_incident_fields(
        incident_id,
        {
            "approval_status": "APPROVED",
            "approval": {
                "approved_by": approval.approved_by,
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "comment": approval.comment,
            },
            "lifecycle_stage": "APPROVED_REMEDIATING",
        },
    )

    plan = await execute_remediation_plan(plan)
    incident.transition_to(IncidentStatus.RESOLVED)
    validation = await ValidationAgent().run(
        ValidationInput(
            incident=incident,
            rca=rca,
            decision=approved_decision,
            remediation_plan=plan,
        ),
        context,
    )
    communication = await CommunicationAgent().run(
        CommunicationInput(
            incident=incident,
            rca=rca,
            decision=approved_decision,
            remediation_plan=plan,
            validation=validation,
        ),
        context,
    )

    result = PipelineResult(
        incident=incident,
        rca=rca,
        decision=approved_decision,
        remediation_plan=plan,
        validation=validation,
        communication=communication,
        remediation_executed=True,
        human_approval_needed=False,
    )
    get_observability().record_pipeline_result(result)

    await store.update_incident_fields(
        incident_id,
        {
            "status": IncidentStatus.RESOLVED.value,
            "lifecycle_stage": "APPROVED_REMEDIATED",
            "approval_status": "APPROVED",
            "decision_after_approval": approved_decision,
            "remediation_plan": plan,
            "validation": validation,
            "communication": communication,
            "remediation_executed": True,
            "human_approval_needed": False,
        },
    )

    return ApprovalResponseSchema(
        incident_id=incident_id,
        approval_status="APPROVED",
        status=IncidentStatus.RESOLVED.value,
        remediation_executed=True,
        validation_status=validation.status,
        communication_channels=communication.channels,
        message="Approval accepted. Remediation executed and validation completed.",
    )


@router.post(
    "/{incident_id}/reject",
    response_model=ApprovalResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Reject a human-in-the-loop remediation plan",
)
async def reject_incident(
    incident_id: str,
    approval: ApprovalRequestSchema,
    settings: Settings = Depends(get_settings),
) -> ApprovalResponseSchema:
    store = _store(settings)
    document = await store.get_incident(incident_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Incident not found: {incident_id}")
    if document.get("decision") != Decision.HUMAN_APPROVAL.value:
        raise HTTPException(
            status_code=409,
            detail="Incident is not waiting for human approval",
        )
    if document.get("approval_status") == "APPROVED":
        raise HTTPException(status_code=409, detail="Incident is already approved")

    rejected_at = datetime.now(timezone.utc).isoformat()
    await store.update_incident_fields(
        incident_id,
        {
            "status": IncidentStatus.ESCALATED.value,
            "lifecycle_stage": "APPROVAL_REJECTED",
            "approval_status": "REJECTED",
            "approval": {
                "rejected_by": approval.approved_by,
                "rejected_at": rejected_at,
                "comment": approval.comment,
            },
            "remediation_executed": False,
            "human_approval_needed": False,
        },
    )

    return ApprovalResponseSchema(
        incident_id=incident_id,
        approval_status="REJECTED",
        status=IncidentStatus.ESCALATED.value,
        remediation_executed=False,
        validation_status=None,
        communication_channels=[],
        message="Approval rejected. Remediation was not executed.",
    )


@router.get(
    "/history",
    summary="Return sample incident history",
)
async def get_history() -> list[dict]:
    fpath = Path("./data/sample_incidents/incidents.json")
    if not fpath.exists():
        return []
    return json.loads(fpath.read_text())
