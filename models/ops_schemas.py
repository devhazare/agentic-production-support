from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Severity(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class ApprovalStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_MORE_INFO = "needs_more_info"


class IncidentEvent(BaseModel):
    incident_id: str = Field(..., min_length=3, max_length=100)
    service_name: str = Field(..., min_length=1, max_length=120)
    severity: Severity
    timestamp: str
    alert_type: str = Field(..., min_length=1, max_length=120)
    metric_name: str = Field(..., min_length=1, max_length=120)
    metric_value: float
    logs_summary: str = Field(default="", max_length=5000)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value


class KnowledgeDocument(BaseModel):
    document_id: str
    title: str
    source_uri: str
    text: str
    score: float = 0.0
    doc_type: Literal["runbook", "rca", "unknown"] = "unknown"


class RCAOutput(BaseModel):
    probable_root_cause: str
    supporting_evidence: list[str] = Field(default_factory=list)
    similar_incident_references: list[str] = Field(default_factory=list)
    recommended_action: str
    recommended_action_type: Literal[
        "restart_service_mock",
        "scale_service_mock",
        "rollback_deployment_mock",
        "drain_queue_mock",
        "none",
    ] = "none"
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "high"]
    citations: list[str] = Field(default_factory=list)


class DecisionOutput(BaseModel):
    route: Literal["human_review", "auto_mock_remediation", "monitor_only", "error"]
    reason: str
    requires_human: bool
    allowed_action: str | None = None


class ApprovalRequest(BaseModel):
    incident_id: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    approver: str | None = None
    comment: str = ""
    requested_at: str = Field(default_factory=utc_now)
    decided_at: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RemediationResult(BaseModel):
    incident_id: str
    action: str
    status: Literal["skipped", "success", "failed"]
    message: str
    executed_at: str = Field(default_factory=utc_now)
    dry_run: bool = True


class AuditLog(BaseModel):
    audit_id: str
    incident_id: str | None = None
    event_type: str
    actor: str = "system"
    timestamp: str = Field(default_factory=utc_now)
    details: dict[str, Any] = Field(default_factory=dict)


class IncidentState(BaseModel):
    incident_id: str
    event: IncidentEvent | None = None
    status: str = "new"
    duplicate: bool = False
    retrieved_documents: list[KnowledgeDocument] = Field(default_factory=list)
    rca: RCAOutput | None = None
    decision: DecisionOutput | None = None
    approval: ApprovalRequest | None = None
    remediation_result: RemediationResult | None = None
    jira_update: dict[str, Any] = Field(default_factory=dict)
    stakeholder_update: str = ""
    rca_summary: str = ""
    decision_path: list[str] = Field(default_factory=list)
    audit_trail: list[AuditLog] = Field(default_factory=list)
    error: str | None = None
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()

