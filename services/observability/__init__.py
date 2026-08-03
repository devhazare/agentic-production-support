"""
services/observability/__init__.py
----------------------------------
Lightweight runtime telemetry for the dashboard.

This is intentionally in-process and dependency-free. It gives the dashboard a
real view of the currently running API process without requiring Prometheus,
OpenTelemetry, or another service for the POC.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from core.config.settings import Settings
from models import PipelineResult


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [jsonable(v) for v in value]
    return value


@dataclass
class AgentActivity:
    timestamp: str
    incident_id: str
    agent: str
    status: str
    duration_ms: int | None = None
    error: str | None = None


@dataclass
class AgentState:
    agent: str
    status: str = "idle"
    incident_id: str | None = None
    last_seen: str = field(default_factory=utc_now)
    duration_ms: int | None = None
    error: str | None = None


@dataclass
class LLMUsage:
    timestamp: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    duration_ms: int
    status: str


@dataclass
class PipelineActivity:
    timestamp: str
    incident_id: str
    service: str
    alert_type: str
    severity: str
    status: str
    decision: str | None
    risk_score: float | None
    validation_status: str | None
    remediation_executed: bool
    human_approval_needed: bool
    pipeline_duration_ms: int


@dataclass
class AnomalyActivity:
    timestamp: str
    source: str
    pattern: str
    occurrences: int
    service: str
    log_snippet: str


class ObservabilityRegistry:
    def __init__(self) -> None:
        self.agent_states: dict[str, AgentState] = {}
        self.agent_activity: deque[AgentActivity] = deque(maxlen=500)
        self.llm_usage: deque[LLMUsage] = deque(maxlen=500)
        self.pipeline_activity: deque[PipelineActivity] = deque(maxlen=500)
        self.anomaly_activity: deque[AnomalyActivity] = deque(maxlen=500)

    def record_agent_start(self, agent: str, incident_id: str) -> None:
        activity = AgentActivity(
            timestamp=utc_now(),
            incident_id=incident_id,
            agent=agent,
            status="running",
        )
        self.agent_activity.append(activity)
        self.agent_states[agent] = AgentState(
            agent=agent,
            status="running",
            incident_id=incident_id,
            last_seen=activity.timestamp,
        )

    def record_agent_done(self, agent: str, incident_id: str, duration_ms: int) -> None:
        activity = AgentActivity(
            timestamp=utc_now(),
            incident_id=incident_id,
            agent=agent,
            status="completed",
            duration_ms=duration_ms,
        )
        self.agent_activity.append(activity)
        self.agent_states[agent] = AgentState(
            agent=agent,
            status="completed",
            incident_id=incident_id,
            last_seen=activity.timestamp,
            duration_ms=duration_ms,
        )

    def record_agent_error(
        self, agent: str, incident_id: str, duration_ms: int, error: str
    ) -> None:
        activity = AgentActivity(
            timestamp=utc_now(),
            incident_id=incident_id,
            agent=agent,
            status="failed",
            duration_ms=duration_ms,
            error=error,
        )
        self.agent_activity.append(activity)
        self.agent_states[agent] = AgentState(
            agent=agent,
            status="failed",
            incident_id=incident_id,
            last_seen=activity.timestamp,
            duration_ms=duration_ms,
            error=error,
        )

    def record_llm_usage(
        self,
        *,
        provider: str,
        model: str,
        prompt: str,
        response: str,
        duration_ms: int,
        status: str,
    ) -> None:
        prompt_tokens = estimate_tokens(prompt)
        completion_tokens = estimate_tokens(response)
        self.llm_usage.append(
            LLMUsage(
                timestamp=utc_now(),
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                duration_ms=duration_ms,
                status=status,
            )
        )

    def record_pipeline_result(self, result: PipelineResult) -> None:
        incident = result.incident
        self.pipeline_activity.append(
            PipelineActivity(
                timestamp=utc_now(),
                incident_id=incident.incident_id,
                service=incident.service,
                alert_type=incident.alert_type,
                severity=incident.severity.value,
                status=incident.status.value,
                decision=result.decision.decision.value if result.decision else None,
                risk_score=result.decision.risk_score if result.decision else None,
                validation_status=result.validation.status if result.validation else None,
                remediation_executed=result.remediation_executed,
                human_approval_needed=result.human_approval_needed,
                pipeline_duration_ms=result.pipeline_duration_ms,
            )
        )

    def record_anomaly(
        self,
        *,
        source: str,
        pattern: str,
        occurrences: int,
        service: str,
        log_snippet: str,
    ) -> None:
        self.anomaly_activity.append(
            AnomalyActivity(
                timestamp=utc_now(),
                source=source,
                pattern=pattern,
                occurrences=occurrences,
                service=service,
                log_snippet=log_snippet,
            )
        )

    def snapshot(self, settings: Settings) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)
        pipelines = list(self.pipeline_activity)
        anomalies = list(self.anomaly_activity)
        recent_anomalies = [
            a for a in anomalies if datetime.fromisoformat(a.timestamp) >= one_hour_ago
        ]
        llm_events = list(self.llm_usage)
        decisions = Counter(p.decision or "UNKNOWN" for p in pipelines)
        severities = Counter(p.severity for p in pipelines)
        source_counts = Counter(a.source for a in anomalies)

        total_tokens = sum(e.total_tokens for e in llm_events)
        prompt_tokens = sum(e.prompt_tokens for e in llm_events)
        completion_tokens = sum(e.completion_tokens for e in llm_events)

        return {
            "generated_at": utc_now(),
            "system": {
                "environment": settings.environment.value,
                "mode": settings.app_mode.value,
                "llm_provider": settings.llm_provider.value,
                "llm_model": self._llm_model(settings),
                "vector_store": settings.vector_store.value,
                "mongodb_enabled": settings.mongodb_enabled,
            },
            "metrics": {
                "incidents_total": len(pipelines),
                "incidents_open": sum(1 for p in pipelines if p.status not in {"RESOLVED"}),
                "auto_resolved": sum(1 for p in pipelines if p.remediation_executed),
                "human_approval": sum(1 for p in pipelines if p.human_approval_needed),
                "anomalies_1h": len(recent_anomalies),
                "llm_calls": len(llm_events),
                "llm_total_tokens": total_tokens,
                "llm_prompt_tokens": prompt_tokens,
                "llm_completion_tokens": completion_tokens,
            },
            "agents": [jsonable(v) for v in self.agent_states.values()],
            "agent_activity": [jsonable(v) for v in reversed(self.agent_activity)],
            "incidents": [jsonable(v) for v in reversed(self.pipeline_activity)],
            "anomalies": [jsonable(v) for v in reversed(self.anomaly_activity)],
            "llm_usage": [jsonable(v) for v in reversed(self.llm_usage)],
            "distributions": {
                "decisions": dict(decisions),
                "severities": dict(severities),
                "anomaly_sources": dict(source_counts),
            },
            "log_sources": log_source_status(settings),
        }

    @staticmethod
    def _llm_model(settings: Settings) -> str:
        if settings.llm_provider.value == "ollama":
            return settings.ollama_model
        if settings.llm_provider.value == "openai":
            return settings.openai_model
        if settings.llm_provider.value == "anthropic":
            return settings.anthropic_model
        return "unknown"


def log_source_status(settings: Settings) -> list[dict[str, Any]]:
    sources = [
        ("magento", "exception.log", settings.magento_exception_log_path),
        ("magento", "system.log", settings.magento_system_log_path),
        ("magento", "access.log", settings.magento_access_log_path),
        ("aem", "error.log", settings.aem_log_path),
        ("java", "application.log", settings.java_log_path),
        ("python", "service.log", settings.python_log_path),
    ]
    rows: list[dict[str, Any]] = []
    for source, name, raw_path in sources:
        configured = bool(raw_path and raw_path != "disabled")
        path = Path(raw_path) if configured else None
        exists = bool(path and path.exists())
        stat = path.stat() if exists and path else None
        rows.append(
            {
                "source": source,
                "name": name,
                "path": str(raw_path),
                "configured": configured,
                "exists": exists,
                "status": "tailing" if exists else ("missing" if configured else "disabled"),
                "size_bytes": stat.st_size if stat else 0,
                "modified_at": (
                    datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()
                    if stat
                    else None
                ),
            }
        )
    return rows


_registry: ObservabilityRegistry | None = None


def get_observability() -> ObservabilityRegistry:
    global _registry
    if _registry is None:
        _registry = ObservabilityRegistry()
    return _registry
