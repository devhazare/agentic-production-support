from __future__ import annotations

import json

from core.config.settings import Settings
from models import IncidentState, RemediationResult, utc_now

SUPPORTED_ACTIONS = {
    "restart_service_mock",
    "scale_service_mock",
    "rollback_deployment_mock",
    "drain_queue_mock",
}


class SlackApprovalMock:
    def create_payload(self, state: IncidentState) -> dict[str, object]:
        return {
            "channel": "#incident-approvals",
            "incident_id": state.incident_id,
            "text": f"Approval requested for {state.event.service_name if state.event else state.incident_id}",
            "actions": ["approved", "rejected", "needs_more_info"],
            "decision": state.decision.model_dump() if state.decision else {},
            "rca": state.rca.model_dump() if state.rca else {},
        }


class JiraMock:
    def build_update(self, state: IncidentState) -> dict[str, object]:
        return {
            "ticket_key": f"OPS-{state.incident_id.replace('INC-', '')}",
            "status": state.status,
            "summary": state.rca_summary,
            "labels": ["ai-ops", "mvp", state.event.severity.value.lower() if state.event else "unknown"],
            "updated_at": utc_now(),
        }


class MockRemediationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings

    def execute(self, incident_id: str, action: str | None) -> RemediationResult:
        if action not in SUPPORTED_ACTIONS:
            return RemediationResult(
                incident_id=incident_id,
                action=action or "none",
                status="skipped",
                message="No supported mock remediation action selected.",
            )
        if self.settings and self.settings.use_aws:
            import boto3

            client = boto3.client("lambda", region_name=self.settings.aws_region)
            client.invoke(
                FunctionName=self.settings.remediation_lambda_name,
                InvocationType="Event",
                Payload=json.dumps(
                    {"incident_id": incident_id, "action": action, "dry_run": True}
                ).encode("utf-8"),
            )
            return RemediationResult(
                incident_id=incident_id,
                action=action,
                status="success",
                message=f"Invoked mock remediation Lambda for {action}; payload is dry-run only.",
            )
        return RemediationResult(
            incident_id=incident_id,
            action=action,
            status="success",
            message=f"Dry-run remediation completed for {action}; no production resources changed.",
        )
