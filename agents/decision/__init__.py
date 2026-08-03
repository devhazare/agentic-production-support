"""
agents/decision/__init__.py
----------------------------
Decision Agent — maps severity × confidence → action.

Pattern: Strategy (DecisionMatrix) + Policy Object.
The matrix is a pure value object — swap it without changing the agent.
"""

from __future__ import annotations

from agents.base import AgentContext, BaseAgent
from core.events import DecisionMadeEvent, get_event_bus
from models import Decision, DecisionResult, Incident, RCAResult, Severity

_RISK_SCORES: dict[Severity, float] = {
    Severity.CRITICAL: 1.0,
    Severity.HIGH: 0.75,
    Severity.MEDIUM: 0.5,
    Severity.LOW: 0.2,
}

# Severity × Confidence → Decision
_MATRIX: dict[tuple[Severity, str], Decision] = {
    (Severity.CRITICAL, "HIGH"):   Decision.HUMAN_APPROVAL,
    (Severity.CRITICAL, "MEDIUM"): Decision.HUMAN_APPROVAL,
    (Severity.CRITICAL, "LOW"):    Decision.HUMAN_APPROVAL,
    (Severity.HIGH,     "HIGH"):   Decision.AUTO_REMEDIATE,
    (Severity.HIGH,     "MEDIUM"): Decision.HUMAN_APPROVAL,
    (Severity.HIGH,     "LOW"):    Decision.HUMAN_APPROVAL,
    (Severity.MEDIUM,   "HIGH"):   Decision.AUTO_REMEDIATE,
    (Severity.MEDIUM,   "MEDIUM"): Decision.AUTO_REMEDIATE,
    (Severity.MEDIUM,   "LOW"):    Decision.MONITOR_ONLY,
    (Severity.LOW,      "HIGH"):   Decision.MONITOR_ONLY,
    (Severity.LOW,      "MEDIUM"): Decision.MONITOR_ONLY,
    (Severity.LOW,      "LOW"):    Decision.MONITOR_ONLY,
}

_REASONS: dict[Decision, str] = {
    Decision.AUTO_REMEDIATE: (
        "Severity and confidence are sufficient for automated remediation."
    ),
    Decision.HUMAN_APPROVAL: (
        "High severity or low confidence — human review required before action."
    ),
    Decision.MONITOR_ONLY: (
        "Low severity — monitoring only, no active intervention needed."
    ),
}


class DecisionAgent(BaseAgent[tuple[Incident, RCAResult], DecisionResult]):
    """
    Evaluates severity × confidence and returns a Decision.
    Input: (Incident, RCAResult) tuple.
    """

    def __init__(self) -> None:
        super().__init__()
        self._bus = get_event_bus()

    async def _execute(
        self,
        input_data: tuple[Incident, RCAResult],
        context: AgentContext,
    ) -> DecisionResult:
        incident, rca = input_data
        confidence = rca.confidence.upper()

        key = (incident.severity, confidence)
        decision = _MATRIX.get(key, Decision.HUMAN_APPROVAL)
        risk_score = _RISK_SCORES.get(incident.severity, 0.5)

        result = DecisionResult(
            incident_id=incident.incident_id,
            decision=decision,
            reason=_REASONS[decision],
            risk_score=risk_score,
        )

        context.set("decision_result", result)
        self._logger.info(
            "decision.made",
            incident_id=incident.incident_id,
            decision=decision.value,
            severity=incident.severity.value,
            confidence=confidence,
            risk_score=risk_score,
        )
        return result

    async def _post_execute(
        self, result: DecisionResult, context: AgentContext
    ) -> None:
        await self._bus.publish(
            DecisionMadeEvent(
                incident_id=result.incident_id,
                decision=result.decision.value,
                risk_score=result.risk_score,
            )
        )
