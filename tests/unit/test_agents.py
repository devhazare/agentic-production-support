"""
tests/unit/test_agents.py
--------------------------
Unit tests for each agent in isolation.

Pattern: each agent is tested with mock dependencies injected —
no LLM calls, no FAISS reads, no real log files.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agents.base import AgentContext
from agents.decision import DecisionAgent
from agents.detection import IncidentDetectionAgent, SeverityScorer
from models import (
    AlertPayloadSchema,
    ContextChunk,
    Decision,
    Incident,
    RCAResult,
    Severity,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_context(incident_id: str = "TEST-001") -> AgentContext:
    return AgentContext(incident_id=incident_id)


def make_payload(**kwargs) -> AlertPayloadSchema:
    defaults = {
        "service": "test-svc",
        "alert_type": "CPUUtilization",
        "metrics": {"cpu_percent": 50.0, "error_rate": 0.01},
    }
    defaults.update(kwargs)
    return AlertPayloadSchema(**defaults)


# ── SeverityScorer ────────────────────────────────────────────────────────────

class TestSeverityScorer:
    def setup_method(self):
        self.scorer = SeverityScorer()

    def test_service_down_is_critical(self):
        from models import Metrics
        m = Metrics(cpu_percent=0.0)
        assert self.scorer.score(m, "ServiceDown") == Severity.CRITICAL

    def test_high_cpu_is_high(self):
        from models import Metrics
        m = Metrics(cpu_percent=92.0)
        assert self.scorer.score(m, "CPUUtilization") == Severity.HIGH

    def test_low_metrics_is_low(self):
        from models import Metrics
        m = Metrics(cpu_percent=20.0, error_rate=0.01, latency_p99_ms=100.0)
        assert self.scorer.score(m, "Custom") == Severity.LOW

    def test_combined_high_scores_critical(self):
        from models import Metrics
        m = Metrics(cpu_percent=95.0, error_rate=0.35, latency_p99_ms=11000.0)
        assert self.scorer.score(m, "CPUUtilization") == Severity.CRITICAL


# ── IncidentDetectionAgent ────────────────────────────────────────────────────

class TestIncidentDetectionAgent:
    @pytest.mark.asyncio
    async def test_creates_incident_with_correct_service(self):
        agent = IncidentDetectionAgent()
        payload = make_payload(service="payment-svc", alert_type="CPUUtilization",
                               metrics={"cpu_percent": 93.0})
        ctx = make_context()
        incident = await agent.run(payload, ctx)
        assert incident.service == "payment-svc"
        assert incident.alert_type == "CPUUtilization"
        assert incident.severity in (Severity.HIGH, Severity.CRITICAL)

    @pytest.mark.asyncio
    async def test_respects_explicit_severity(self):
        agent = IncidentDetectionAgent()
        payload = make_payload(severity="LOW")
        ctx = make_context()
        incident = await agent.run(payload, ctx)
        assert incident.severity == Severity.LOW

    @pytest.mark.asyncio
    async def test_invalid_severity_raises(self):
        with pytest.raises(ValidationError):
            make_payload(severity="BANANA")


# ── DecisionAgent ─────────────────────────────────────────────────────────────

class TestDecisionAgent:
    def _make_incident(self, severity: Severity) -> Incident:
        from models import Incident
        return Incident(service="svc", alert_type="CPU", severity=severity)

    def _make_rca(self, confidence: str) -> RCAResult:
        return RCAResult(
            incident_id="INC-001",
            rca_text="root cause text",
            confidence=confidence,
            context_chunks=[],
        )

    @pytest.mark.asyncio
    async def test_high_severity_high_confidence_auto_remediate(self):
        agent = DecisionAgent()
        inc = self._make_incident(Severity.HIGH)
        rca = self._make_rca("HIGH")
        result = await agent.run((inc, rca), make_context())
        assert result.decision == Decision.AUTO_REMEDIATE

    @pytest.mark.asyncio
    async def test_critical_always_human_approval(self):
        agent = DecisionAgent()
        inc = self._make_incident(Severity.CRITICAL)
        for confidence in ("HIGH", "MEDIUM", "LOW"):
            rca = self._make_rca(confidence)
            result = await agent.run((inc, rca), make_context())
            assert result.decision == Decision.HUMAN_APPROVAL

    @pytest.mark.asyncio
    async def test_low_severity_monitor_only(self):
        agent = DecisionAgent()
        inc = self._make_incident(Severity.LOW)
        rca = self._make_rca("HIGH")
        result = await agent.run((inc, rca), make_context())
        assert result.decision == Decision.MONITOR_ONLY

    @pytest.mark.asyncio
    async def test_risk_score_set_correctly(self):
        agent = DecisionAgent()
        inc = self._make_incident(Severity.HIGH)
        rca = self._make_rca("HIGH")
        result = await agent.run((inc, rca), make_context())
        assert result.risk_score == 0.75
