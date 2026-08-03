"""
agents/remediation/__init__.py
--------------------------------
Remediation Agent — generates and executes remediation plans.

Patterns:
  - Template Method (BaseAgent)
  - Command pattern: each RemediationStep is a Command that can be executed
    or simulated independently.
  - Strategy: ActionExecutor is swappable (SimulatedExecutor / KubernetesExecutor)
"""

from __future__ import annotations

import abc
import asyncio
import re
import time
from dataclasses import dataclass

from agents.base import AgentContext, BaseAgent
from agents.rca import PromptBuilder
from core.events import RemediationCompletedEvent, get_event_bus
from core.exceptions import RemediationError
from models import (
    Decision,
    DecisionResult,
    Incident,
    RCAResult,
    RemediationPlan,
    RemediationStep,
    StepStatus,
)
from rag.retriever import RAGRetriever
from services.llm import LLMService

_SYSTEM_PROMPT = """\
You are an automated remediation engine for cloud-native platforms (AWS, Kubernetes,
Magento, AEM, Java, Python). Generate a precise, ordered remediation plan.
Prefix each step: [SCALE] [RESTART] [ROLLBACK] [CONFIG] [ALERT] [INVESTIGATE]
End with: ESTIMATED_MTTR: <N>
"""

_ACTION_TYPES = {"SCALE", "RESTART", "ROLLBACK", "CONFIG", "ALERT", "INVESTIGATE"}
_MTTR_RE = re.compile(r"ESTIMATED_MTTR[:\s]+(\d+)", re.IGNORECASE)
_STEP_RE = re.compile(r"\[(" + "|".join(_ACTION_TYPES) + r")\](.*)", re.IGNORECASE)


# ── Command pattern: ActionExecutor ──────────────────────────────────────────

class ActionExecutor(abc.ABC):
    """Strategy interface for executing a remediation step."""

    @abc.abstractmethod
    async def execute(self, step: RemediationStep) -> bool:
        """Execute step. Returns True on success."""


class SimulatedExecutor(ActionExecutor):
    """Simulates all actions — safe for POC and staging."""

    async def execute(self, step: RemediationStep) -> bool:
        step.status = StepStatus.RUNNING
        await asyncio.sleep(0.3)  # simulate work
        step.status = StepStatus.DONE
        return True


class DryRunExecutor(ActionExecutor):
    """Logs what would happen but does nothing."""

    async def execute(self, step: RemediationStep) -> bool:
        step.status = StepStatus.SKIPPED
        return True


async def execute_remediation_plan(
    plan: RemediationPlan,
    executor: ActionExecutor | None = None,
) -> RemediationPlan:
    """Execute an already generated plan after human approval."""
    action_executor = executor or SimulatedExecutor()
    for step in plan.steps:
        t0 = time.perf_counter()
        success = await action_executor.execute(step)
        step.duration_ms = int((time.perf_counter() - t0) * 1000)
        if not success:
            step.status = StepStatus.FAILED
    plan.executed = True
    return plan


# ── Agent ─────────────────────────────────────────────────────────────────────

@dataclass
class RemediationInput:
    incident: Incident
    rca: RCAResult
    decision: DecisionResult


class RemediationAgent(BaseAgent[RemediationInput, RemediationPlan]):
    """
    Generates a remediation plan via LLM + RAG, then executes it
    using the injected ActionExecutor strategy.
    """

    def __init__(
        self,
        llm: LLMService,
        retriever: RAGRetriever,
        executor: ActionExecutor | None = None,
    ) -> None:
        super().__init__()
        self._llm = llm
        self._retriever = retriever
        self._executor = executor or SimulatedExecutor()
        self._bus = get_event_bus()

    async def _execute(
        self, input_data: RemediationInput, context: AgentContext
    ) -> RemediationPlan:
        incident = input_data.incident
        rca = input_data.rca
        decision = input_data.decision

        # Generate plan regardless of decision
        plan = await self._generate_plan(incident, rca)

        # Execute only if decision permits
        if decision.decision == Decision.AUTO_REMEDIATE:
            plan = await self._execute_plan(plan)
        else:
            for step in plan.steps:
                step.status = StepStatus.SKIPPED

        context.set("remediation_plan", plan)
        self._logger.info(
            "remediation.complete",
            incident_id=incident.incident_id,
            steps=len(plan.steps),
            executed=plan.executed,
            mttr=plan.estimated_mttr_minutes,
        )
        return plan

    async def _post_execute(
        self, result: RemediationPlan, context: AgentContext
    ) -> None:
        await self._bus.publish(
            RemediationCompletedEvent(
                incident_id=result.incident_id,
                steps_executed=result.completed_steps,
                mttr_minutes=result.estimated_mttr_minutes,
            )
        )

    async def _generate_plan(
        self, incident: Incident, rca: RCAResult
    ) -> RemediationPlan:
        query = f"remediation {incident.alert_type} {incident.service}"
        chunks = await self._retriever.retrieve(query, top_k=3)
        context_text = "\n\n".join(c.text for c in chunks)

        prompt = PromptBuilder.remediation_prompt(incident, rca.rca_text, context_text)
        plan_text = await self._llm.generate(
            prompt=prompt, system=_SYSTEM_PROMPT, temperature=0.15
        )

        if not plan_text:
            raise RemediationError("LLM returned empty remediation plan")

        steps = self._parse_steps(plan_text)
        mttr = self._parse_mttr(plan_text)

        return RemediationPlan(
            incident_id=incident.incident_id,
            steps=steps,
            llm_plan_text=plan_text,
            estimated_mttr_minutes=mttr,
        )

    async def _execute_plan(self, plan: RemediationPlan) -> RemediationPlan:
        return await execute_remediation_plan(plan, self._executor)

    @staticmethod
    def _parse_steps(plan_text: str) -> list[RemediationStep]:
        steps: list[RemediationStep] = []
        for line in plan_text.splitlines():
            m = _STEP_RE.match(line.strip())
            if m:
                steps.append(
                    RemediationStep(
                        step_number=len(steps) + 1,
                        action_type=m.group(1).upper(),
                        description=m.group(2).strip(),
                    )
                )
        return steps[:6]

    @staticmethod
    def _parse_mttr(plan_text: str) -> int:
        m = _MTTR_RE.search(plan_text)
        return int(m.group(1)) if m else 15
