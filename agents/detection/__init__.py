"""
agents/detection/__init__.py
-----------------------------
Incident Detection Agent — normalises alert payloads and scores severity.

Patterns: Template Method (inherits BaseAgent), Strategy (scoring algorithm),
Chain of Responsibility (log-source enrichment chain).
"""

from __future__ import annotations

from agents.base import AgentContext, BaseAgent
from core.events import IncidentDetectedEvent, get_event_bus
from core.exceptions import IncidentDetectionError
from models import (
    AlertPayloadSchema,
    Incident,
    LogSource,
    Metrics,
    Severity,
)


# ── Severity scoring strategy ─────────────────────────────────────────────────

class SeverityScorer:
    """
    Strategy: encapsulates the severity scoring algorithm.
    Swap implementations without touching the agent.
    """

    _WEIGHTS = {
        "cpu_high": (90, 85, 70),       # (CRITICAL, HIGH, MEDIUM thresholds)
        "error_rate": (0.3, 0.1, 0.05),
        "latency": (10_000, 5_000, 2_000),
        "db_utilisation": (0.95, 0.80, 0.60),
    }

    def score(self, metrics: Metrics, alert_type: str) -> Severity:
        if alert_type == "ServiceDown":
            return Severity.CRITICAL

        points = 0

        cpu = metrics.cpu_percent
        if cpu > self._WEIGHTS["cpu_high"][0]:
            points += 4
        elif cpu > self._WEIGHTS["cpu_high"][1]:
            points += 2
        elif cpu > self._WEIGHTS["cpu_high"][2]:
            points += 1

        err = metrics.error_rate
        if err > self._WEIGHTS["error_rate"][0]:
            points += 3
        elif err > self._WEIGHTS["error_rate"][1]:
            points += 2
        elif err > self._WEIGHTS["error_rate"][2]:
            points += 1

        lat = metrics.latency_p99_ms
        if lat > self._WEIGHTS["latency"][0]:
            points += 3
        elif lat > self._WEIGHTS["latency"][1]:
            points += 2
        elif lat > self._WEIGHTS["latency"][2]:
            points += 1

        if metrics.db_utilisation > self._WEIGHTS["db_utilisation"][0]:
            points += 3

        if points >= 7:
            return Severity.CRITICAL
        if points >= 4:
            return Severity.HIGH
        if points >= 2:
            return Severity.MEDIUM
        return Severity.LOW


# ── Agent ─────────────────────────────────────────────────────────────────────

class IncidentDetectionAgent(BaseAgent[AlertPayloadSchema, Incident]):
    """
    Parses an alert payload and returns a structured Incident entity.

    Responsibilities (Single Responsibility Principle):
      - Parse raw payload into typed Metrics
      - Score severity (delegated to SeverityScorer strategy)
      - Publish IncidentDetectedEvent (delegated to EventBus)
    """

    def __init__(self, scorer: SeverityScorer | None = None) -> None:
        super().__init__()
        self._scorer = scorer or SeverityScorer()
        self._bus = get_event_bus()

    async def _execute(
        self, payload: AlertPayloadSchema, context: AgentContext
    ) -> Incident:
        metrics = Metrics(
            cpu_percent=payload.metrics.get("cpu_percent", 0.0),
            memory_mb=payload.metrics.get("memory_mb", 0.0),
            error_rate=payload.metrics.get("error_rate", 0.0),
            latency_p99_ms=payload.metrics.get("latency_p99_ms", 0.0),
            db_connections=int(payload.metrics.get("db_connections", 0)),
            db_max_connections=int(payload.metrics.get("db_max_connections", 100)),
        )

        if payload.severity:
            try:
                severity = Severity(payload.severity.upper())
            except ValueError as exc:
                raise IncidentDetectionError(
                    f"Invalid severity value: {payload.severity}"
                ) from exc
        else:
            severity = self._scorer.score(metrics, payload.alert_type)

        log_source: LogSource | None = None
        if payload.log_source:
            try:
                log_source = LogSource(payload.log_source.lower())
            except ValueError:
                pass

        incident = Incident(
            incident_id=payload.incident_id or f"INC-{context.incident_id[-8:].upper()}",
            service=payload.service,
            alert_type=payload.alert_type,
            severity=severity,
            metrics=metrics,
            logs_snippet=payload.logs_snippet,
            log_source=log_source,
            raw_payload=payload.model_dump(),
        )

        self._logger.info(
            "incident.created",
            incident_id=incident.incident_id,
            severity=severity.value,
            service=incident.service,
        )
        return incident

    async def _post_execute(
        self, result: Incident, context: AgentContext
    ) -> None:
        await self._bus.publish(
            IncidentDetectedEvent(
                incident_id=result.incident_id,
                service=result.service,
                alert_type=result.alert_type,
                severity=result.severity.value,
                source=result.log_source.value if result.log_source else "metric",
            )
        )


# ── Mock helpers (used by API router and CLI) ─────────────────────────────────

_MOCK_INCIDENTS = MOCK_INCIDENTS = [
    {
        "service": "payment-service",
        "alert_type": "CPUUtilization",
        "metrics": {"cpu_percent": 93.0, "error_rate": 0.03, "latency_p99_ms": 4500},
        "logs_snippet": "ERROR: Thread pool exhausted. Queue size: 512.",
    },
    {
        "service": "user-service",
        "alert_type": "MemoryUtilization",
        "metrics": {"cpu_percent": 42.0, "memory_mb": 3900.0, "error_rate": 0.18},
        "logs_snippet": "WARN: GC overhead limit exceeded. java.lang.OutOfMemoryError",
        "log_source": "java",
    },
    {
        "service": "order-service",
        "alert_type": "DatabaseConnections",
        "metrics": {"cpu_percent": 28.0, "error_rate": 0.45, "db_connections": 198.0, "db_max_connections": 200.0},
        "logs_snippet": "ERROR: HikariPool-1 Connection not available, timed out after 30000ms",
        "log_source": "java",
    },
    {
        "service": "magento-checkout",
        "alert_type": "LogAnomaly",
        "metrics": {"error_rate": 0.12},
        "logs_snippet": "main.ERROR: SQLSTATE[HY000]: Lock wait timeout exceeded",
        "log_source": "magento",
    },
]

import random as _random

def generate_mock_incident() -> dict:
    import copy
    return copy.deepcopy(_random.choice(_MOCK_INCIDENTS))
