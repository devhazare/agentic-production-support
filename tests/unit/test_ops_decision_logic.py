from __future__ import annotations

from agents.ops_nodes import decision_agent
from models.ops_schemas import IncidentEvent, IncidentState, RCAOutput


def make_state(severity: str, confidence: float, risk: str = "low") -> IncidentState:
    event = IncidentEvent(
        incident_id=f"INC-{severity}-{confidence}",
        service_name="svc",
        severity=severity,
        timestamp="2026-06-27T10:00:00Z",
        alert_type="LatencySpike",
        metric_name="p99_latency_ms",
        metric_value=1000,
        logs_summary="database connection timeout",
    )
    state = IncidentState(incident_id=event.incident_id, event=event)
    state.rca = RCAOutput(
        probable_root_cause="pool exhaustion",
        supporting_evidence=["timeout"],
        recommended_action="scale",
        recommended_action_type="scale_service_mock",
        confidence_score=confidence,
        risk_level=risk,
        citations=["s3://x"],
    )
    return state


def test_high_severity_requires_human_review() -> None:
    state = decision_agent(make_state("High", 0.95, "low"))
    assert state.decision is not None
    assert state.decision.route == "human_review"
    assert state.decision.requires_human is True


def test_low_confidence_requires_human_review() -> None:
    state = decision_agent(make_state("Low", 0.5, "low"))
    assert state.decision is not None
    assert state.decision.route == "human_review"


def test_low_risk_high_confidence_allows_mock_remediation() -> None:
    state = decision_agent(make_state("Low", 0.9, "low"))
    assert state.decision is not None
    assert state.decision.route == "auto_mock_remediation"
    assert state.decision.allowed_action == "scale_service_mock"

