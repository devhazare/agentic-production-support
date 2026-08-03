"""
models/__init__.py
------------------
Domain model layer — pure Python dataclasses / Pydantic models.

Pattern: Domain Model + Value Objects
- No business logic here — only data shape and validation
- Immutable where possible (frozen=True)
- Pydantic for serialisation/validation, dataclasses for internal use
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


# ── Enumerations ─────────────────────────────────────────────────────────────

class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def numeric(self) -> int:
        return {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}[self.value]


class Decision(str, Enum):
    AUTO_REMEDIATE = "AUTO_REMEDIATE"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    MONITOR_ONLY = "MONITOR_ONLY"


class IncidentStatus(str, Enum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    REMEDIATING = "REMEDIATING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


class LogSource(str, Enum):
    MAGENTO = "magento"
    AEM = "aem"
    JAVA = "java"
    PYTHON = "python"
    CLOUDWATCH = "cloudwatch"
    PROMETHEUS = "prometheus"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


# ── Value Objects (immutable) ────────────────────────────────────────────────

@dataclass(frozen=True)
class Metrics:
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    error_rate: float = 0.0
    latency_p99_ms: float = 0.0
    db_connections: int = 0
    db_max_connections: int = 100

    @property
    def db_utilisation(self) -> float:
        if self.db_max_connections == 0:
            return 0.0
        return self.db_connections / self.db_max_connections


@dataclass(frozen=True)
class LogLine:
    source: LogSource
    level: str
    message: str
    raw: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    service: str = ""
    trace_id: str = ""


@dataclass(frozen=True)
class ContextChunk:
    text: str
    source: str
    chunk_id: str
    score: float = 0.0


# ── Entities ─────────────────────────────────────────────────────────────────

@dataclass
class Incident:
    """
    Core domain entity.
    Pattern: Entity — has identity (incident_id), mutable lifecycle state.
    """

    service: str
    alert_type: str
    severity: Severity
    incident_id: str = field(default_factory=lambda: f"INC-{uuid4().hex[:8].upper()}")
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: IncidentStatus = IncidentStatus.OPEN
    metrics: Metrics = field(default_factory=Metrics)
    logs_snippet: str = ""
    log_source: LogSource | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def transition_to(self, status: IncidentStatus) -> None:
        self.status = status

    def summary(self) -> str:
        return (
            f"[{self.incident_id}] {self.service} | {self.alert_type} | "
            f"Severity: {self.severity.value} | Status: {self.status.value}\n"
            f"Log snippet: {self.logs_snippet[:200]}"
        )


@dataclass
class RCAResult:
    incident_id: str
    rca_text: str
    confidence: str
    context_chunks: list[ContextChunk] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class DecisionResult:
    incident_id: str
    decision: Decision
    reason: str
    risk_score: float


@dataclass
class RemediationStep:
    step_number: int
    action_type: str
    description: str
    status: StepStatus = StepStatus.PENDING
    duration_ms: int = 0
    error: str = ""


@dataclass
class RemediationPlan:
    incident_id: str
    steps: list[RemediationStep] = field(default_factory=list)
    llm_plan_text: str = ""
    estimated_mttr_minutes: int = 0
    executed: bool = False

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.DONE)


@dataclass
class ValidationResult:
    incident_id: str
    passed: bool
    status: str
    checks: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CommunicationResult:
    incident_id: str
    channels: list[str] = field(default_factory=list)
    subject: str = ""
    message: str = ""
    report: dict[str, Any] = field(default_factory=dict)
    delivered: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class PipelineResult:
    """Aggregate output of one full orchestration run."""

    incident: Incident
    rca: RCAResult | None = None
    decision: DecisionResult | None = None
    remediation_plan: RemediationPlan | None = None
    validation: ValidationResult | None = None
    communication: CommunicationResult | None = None
    remediation_executed: bool = False
    human_approval_needed: bool = False
    pipeline_duration_ms: int = 0
    error: str | None = None


# ── API Schemas (Pydantic) ────────────────────────────────────────────────────

class AlertPayloadSchema(BaseModel):
    """Inbound alert payload — API contract for POST /api/v1/incidents/analyze."""

    service: str = Field(..., min_length=1, max_length=100, examples=["payment-service"])
    alert_type: str = Field(..., min_length=1, max_length=100, examples=["CPUUtilization"])
    metrics: dict[str, float] = Field(default_factory=dict)
    logs_snippet: str = Field(default="", max_length=2000)
    severity: str | None = Field(default=None, pattern=r"^(LOW|MEDIUM|HIGH|CRITICAL)$")
    incident_id: str | None = None
    log_source: str | None = None

    model_config = {"json_schema_extra": {"example": {
        "service": "payment-service",
        "alert_type": "CPUUtilization",
        "metrics": {"cpu_percent": 93.0, "error_rate": 0.03, "latency_p99_ms": 4500},
        "logs_snippet": "ERROR: Thread pool exhausted. Queue size: 512.",
    }}}


class PipelineResultSchema(BaseModel):
    """Outbound pipeline result — API contract for pipeline response."""

    incident_id: str
    service: str
    severity: str
    status: str
    decision: str | None
    risk_score: float | None
    rca_summary: str | None
    remediation_steps: int
    estimated_mttr_minutes: int
    human_approval_needed: bool
    validation_status: str | None = None
    validation_passed: bool | None = None
    communication_channels: list[str] = Field(default_factory=list)
    pipeline_duration_ms: int
    error: str | None = None


class ApprovalRequestSchema(BaseModel):
    approved_by: str = Field(..., min_length=1, max_length=100)
    comment: str = Field(default="", max_length=1000)


class ApprovalResponseSchema(BaseModel):
    incident_id: str
    approval_status: str
    status: str
    remediation_executed: bool
    validation_status: str | None = None
    communication_channels: list[str] = Field(default_factory=list)
    message: str


class HealthResponseSchema(BaseModel):
    status: str
    environment: str
    llm_provider: str
    llm_status: str
    vector_store: str
    log_sources: list[str]
    version: str = "1.0.0"


class RAGSearchRequestSchema(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)


class RAGSearchResultSchema(BaseModel):
    source: str
    chunk_id: str
    score: float
    text: str


class RAGSearchResponseSchema(BaseModel):
    query: str
    top_k: int
    results: list[RAGSearchResultSchema]


class RAGHealthResponseSchema(BaseModel):
    status: str
    vector_store: str
    knowledge_base_path: str
    index_path: str
    index_exists: bool
    metadata_exists: bool
    embedder_exists: bool
    loaded: bool
    chunk_count: int
    embedder_type: str | None = None
    embedder_dim: int | None = None
    sources: dict[str, int] = Field(default_factory=dict)


class RAGRebuildResponseSchema(BaseModel):
    status: str
    chunk_count: int
    embedder_type: str | None = None
    embedder_dim: int | None = None
    index_path: str
    metadata_path: str
    embedder_path: str


from models.ops_schemas import (  # noqa: E402
    ApprovalRequest,
    ApprovalStatus,
    AuditLog,
    DecisionOutput,
    IncidentEvent,
    IncidentState,
    KnowledgeDocument,
    RCAOutput,
    RemediationResult,
    utc_now,
)
