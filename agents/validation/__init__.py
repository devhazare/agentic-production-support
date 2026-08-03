"""
agents/validation/__init__.py
-----------------------------
Validation Agent — verifies remediation outcome and residual incident risk.
"""

from __future__ import annotations

from dataclasses import dataclass

from agents.base import AgentContext, BaseAgent
from models import (
    Decision,
    DecisionResult,
    Incident,
    RCAResult,
    RemediationPlan,
    StepStatus,
    ValidationResult,
)


@dataclass
class ValidationInput:
    incident: Incident
    rca: RCAResult
    decision: DecisionResult
    remediation_plan: RemediationPlan


class ValidationAgent(BaseAgent[ValidationInput, ValidationResult]):
    """
    Verifies whether the chosen action path produced an acceptable outcome.

    This is deliberately deterministic for now. Later it can call CloudWatch,
    OpenSearch, Kubernetes, synthetic checks, or app health endpoints.
    """

    async def _execute(
        self, input_data: ValidationInput, context: AgentContext
    ) -> ValidationResult:
        incident = input_data.incident
        decision = input_data.decision
        plan = input_data.remediation_plan

        checks: list[dict] = []

        checks.append(
            {
                "name": "rca_confidence_present",
                "passed": bool(input_data.rca.confidence),
                "detail": f"confidence={input_data.rca.confidence}",
            }
        )

        if decision.decision == Decision.AUTO_REMEDIATE:
            checks.append(
                {
                    "name": "remediation_executed",
                    "passed": plan.executed,
                    "detail": f"executed={plan.executed}",
                }
            )
            failed_steps = [s for s in plan.steps if s.status == StepStatus.FAILED]
            checks.append(
                {
                    "name": "remediation_steps_successful",
                    "passed": len(failed_steps) == 0 and plan.completed_steps > 0,
                    "detail": (
                        f"completed={plan.completed_steps}, failed={len(failed_steps)}, "
                        f"total={len(plan.steps)}"
                    ),
                }
            )
        elif decision.decision == Decision.HUMAN_APPROVAL:
            checks.append(
                {
                    "name": "human_approval_required",
                    "passed": True,
                    "detail": "remediation held for approval",
                }
            )
        else:
            checks.append(
                {
                    "name": "monitor_only_path",
                    "passed": True,
                    "detail": "low-risk incident selected for monitoring",
                }
            )

        passed = all(bool(check["passed"]) for check in checks)
        status = "VALIDATED" if passed else "VALIDATION_FAILED"
        summary = (
            f"{status}: {incident.incident_id} decision={decision.decision.value} "
            f"checks_passed={sum(1 for c in checks if c['passed'])}/{len(checks)}"
        )

        result = ValidationResult(
            incident_id=incident.incident_id,
            passed=passed,
            status=status,
            checks=checks,
            summary=summary,
        )
        context.set("validation_result", result)
        self._logger.info(
            "validation.complete",
            incident_id=incident.incident_id,
            status=status,
            passed=passed,
        )
        return result
