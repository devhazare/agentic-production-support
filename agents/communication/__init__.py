"""
agents/communication/__init__.py
--------------------------------
Communication Agent — builds incident update/report payloads.
"""

from __future__ import annotations

from dataclasses import dataclass

from agents.base import AgentContext, BaseAgent
from models import (
    CommunicationResult,
    Decision,
    DecisionResult,
    Incident,
    RCAResult,
    RemediationPlan,
    ValidationResult,
)


@dataclass
class CommunicationInput:
    incident: Incident
    rca: RCAResult
    decision: DecisionResult
    remediation_plan: RemediationPlan
    validation: ValidationResult


class CommunicationAgent(BaseAgent[CommunicationInput, CommunicationResult]):
    """
    Produces the notification/report object for Slack, Teams, email, Jira, etc.

    Delivery is intentionally not implemented here yet. This keeps the pipeline
    honest: communication output is generated and persisted, while external
    connectors can be added later behind a sender interface.
    """

    async def _execute(
        self, input_data: CommunicationInput, context: AgentContext
    ) -> CommunicationResult:
        incident = input_data.incident
        decision = input_data.decision
        plan = input_data.remediation_plan
        validation = input_data.validation

        channels = self._channels_for(decision)
        subject = (
            f"[{incident.severity.value}] {incident.service} "
            f"{incident.alert_type} - {decision.decision.value}"
        )
        message = (
            f"Incident {incident.incident_id} for {incident.service}. "
            f"Decision: {decision.decision.value}. "
            f"Validation: {validation.status}. "
            f"Remediation steps: {len(plan.steps)} planned, {plan.completed_steps} completed."
        )
        report = {
            "incident_id": incident.incident_id,
            "service": incident.service,
            "alert_type": incident.alert_type,
            "severity": incident.severity.value,
            "status": incident.status.value,
            "decision": decision.decision.value,
            "risk_score": decision.risk_score,
            "validation_status": validation.status,
            "validation_passed": validation.passed,
            "rca_confidence": input_data.rca.confidence,
            "rca_summary": input_data.rca.rca_text[:1000],
            "remediation_executed": plan.executed,
            "remediation_steps": [
                {
                    "step_number": step.step_number,
                    "action_type": step.action_type,
                    "description": step.description,
                    "status": step.status.value,
                    "duration_ms": step.duration_ms,
                }
                for step in plan.steps
            ],
        }

        result = CommunicationResult(
            incident_id=incident.incident_id,
            channels=channels,
            subject=subject,
            message=message,
            report=report,
            delivered=False,
        )
        context.set("communication_result", result)
        self._logger.info(
            "communication.prepared",
            incident_id=incident.incident_id,
            channels=channels,
        )
        return result

    @staticmethod
    def _channels_for(decision: DecisionResult) -> list[str]:
        if decision.decision == Decision.HUMAN_APPROVAL:
            return ["slack:oncall", "email:oncall", "jira:approval"]
        if decision.decision == Decision.AUTO_REMEDIATE:
            return ["slack:incidents", "jira:incident"]
        return ["slack:incidents"]
