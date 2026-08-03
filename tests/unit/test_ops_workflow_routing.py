from __future__ import annotations

from pathlib import Path

from core.config.settings import Settings
from models.ops_schemas import IncidentEvent
from services.ops_store import IncidentStore
from orchestration.langgraph_workflow import IncidentWorkflow


def test_workflow_routes_high_severity_to_approval(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_DATA_DIR", "sample_data")
    settings = Settings(local_store_path=tmp_path / "store.json", local_audit_path=tmp_path / "audit.jsonl")
    workflow = IncidentWorkflow(IncidentStore(settings))
    event = IncidentEvent(
        incident_id="INC-TEST-HIGH",
        service_name="checkout-api",
        severity="High",
        timestamp="2026-06-27T10:00:00Z",
        alert_type="LatencySpike",
        metric_name="p99_latency_ms",
        metric_value=4200,
        logs_summary="database connection acquisition timeouts",
    )
    state = workflow.run(event)
    assert state.status == "awaiting_approval"
    assert state.approval is not None
    assert state.remediation_result is None


def test_workflow_can_approve_and_mock_remediate(tmp_path: Path) -> None:
    settings = Settings(local_store_path=tmp_path / "store.json", local_audit_path=tmp_path / "audit.jsonl")
    workflow = IncidentWorkflow(IncidentStore(settings))
    event = IncidentEvent(
        incident_id="INC-TEST-APPROVE",
        service_name="payment-api",
        severity="Critical",
        timestamp="2026-06-27T10:00:00Z",
        alert_type="ErrorRateAfterDeploy",
        metric_name="http_5xx_rate",
        metric_value=20,
        logs_summary="deployment rollback required after release",
    )
    state = workflow.run(event)
    assert state.status == "awaiting_approval"
    approved = workflow.approve(event.incident_id, approver="sre@example.com", comment="approved")
    assert approved.remediation_result is not None
    assert approved.remediation_result.status == "success"
    assert approved.status == "remediated"

