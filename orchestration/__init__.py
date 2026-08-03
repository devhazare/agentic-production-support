"""
orchestration/__init__.py
--------------------------
AI Orchestrator — coordinates all agents in a pipeline run.

Patterns:
  - Chain of Responsibility: each agent is a handler in the chain;
    the orchestrator wires them and manages the AgentContext thread.
  - Facade: hides internal agent wiring from the API layer.
  - Builder: AgentPipelineBuilder constructs the pipeline with DI.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from agents.base import AgentContext
from core.exceptions import OrchestratorError
from core.logging import get_logger
from models import (
    AlertPayloadSchema,
    Decision,
    IncidentStatus,
    PipelineResult,
)
from uuid import uuid4

logger = get_logger(__name__)


class Orchestrator:
    """
    Coordinates the full agent pipeline.

    Chain:
        AlertPayload
          → IncidentDetectionAgent   (detect + score)
          → RCAAgent                 (RAG + LLM analysis)
          → DecisionAgent            (severity × confidence)
          → RemediationAgent         (generate + execute/skip)
          → ValidationAgent          (verify outcome)
          → CommunicationAgent       (prepare updates/report)
          → PipelineResult
    """

    def __init__(
        self,
        detection_agent: Any,
        rca_agent: Any,
        decision_agent: Any,
        remediation_agent: Any,
        validation_agent: Any,
        communication_agent: Any,
    ) -> None:
        self._detection = detection_agent
        self._rca = rca_agent
        self._decision = decision_agent
        self._remediation = remediation_agent
        self._validation = validation_agent
        self._communication = communication_agent

    async def run(self, payload: AlertPayloadSchema) -> PipelineResult:
        run_id = str(uuid4())
        context = AgentContext(incident_id=run_id)
        t0 = time.perf_counter()

        logger.info("pipeline.start", run_id=run_id, service=payload.service)

        try:
            from agents.communication import CommunicationInput  # noqa: PLC0415
            from agents.remediation import RemediationInput  # noqa: PLC0415
            from agents.validation import ValidationInput  # noqa: PLC0415

            # Step 1 — Detection
            incident = await self._detection.run(payload, context)
            incident.transition_to(IncidentStatus.INVESTIGATING)

            # Step 2 — RCA
            rca = await self._rca.run(incident, context)

            # Step 3 — Decision
            decision = await self._decision.run((incident, rca), context)

            # Step 4 — Remediation
            rem_input = RemediationInput(incident=incident, rca=rca, decision=decision)
            plan = await self._remediation.run(rem_input, context)

            human_approval = decision.decision == Decision.HUMAN_APPROVAL
            executed = decision.decision == Decision.AUTO_REMEDIATE

            if executed:
                incident.transition_to(IncidentStatus.RESOLVED)
            elif human_approval:
                incident.transition_to(IncidentStatus.ESCALATED)

            # Step 5 — Validation
            validation_input = ValidationInput(
                incident=incident,
                rca=rca,
                decision=decision,
                remediation_plan=plan,
            )
            validation = await self._validation.run(validation_input, context)

            # Step 6 — Communication/report preparation
            communication_input = CommunicationInput(
                incident=incident,
                rca=rca,
                decision=decision,
                remediation_plan=plan,
                validation=validation,
            )
            communication = await self._communication.run(communication_input, context)

            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.info(
                "pipeline.complete",
                run_id=run_id,
                incident_id=incident.incident_id,
                decision=decision.decision.value,
                validation=validation.status,
                duration_ms=duration_ms,
            )

            result = PipelineResult(
                incident=incident,
                rca=rca,
                decision=decision,
                remediation_plan=plan,
                validation=validation,
                communication=communication,
                remediation_executed=executed,
                human_approval_needed=human_approval,
                pipeline_duration_ms=duration_ms,
            )
            try:
                from services.observability import get_observability  # noqa: PLC0415

                get_observability().record_pipeline_result(result)
            except Exception:
                pass
            return result

        except Exception as exc:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            logger.error(
                "pipeline.error",
                run_id=run_id,
                error=str(exc),
                duration_ms=duration_ms,
            )
            raise OrchestratorError(
                f"Pipeline failed: {exc}", context={"run_id": run_id}
            ) from exc


# ── Builder pattern ───────────────────────────────────────────────────────────

@dataclass
class OrchestratorBuilder:
    """
    Builder: constructs an Orchestrator with all wired dependencies.
    Call .build() to get a ready-to-use Orchestrator.

    Usage:
        orchestrator = (
            OrchestratorBuilder()
            .with_settings(settings)
            .build()
        )
    """

    _settings: object = field(default=None)

    def with_settings(self, settings: object) -> "OrchestratorBuilder":
        self._settings = settings
        return self

    def build(self) -> Orchestrator:
        from agents.communication import CommunicationAgent  # noqa: PLC0415
        from agents.decision import DecisionAgent  # noqa: PLC0415
        from agents.detection import IncidentDetectionAgent  # noqa: PLC0415
        from agents.rca import RCAAgent  # noqa: PLC0415
        from agents.remediation import RemediationAgent  # noqa: PLC0415
        from agents.validation import ValidationAgent  # noqa: PLC0415
        from core.config.settings import get_settings
        from rag.indexer import FAISSIndexer
        from rag.retriever import RAGRetriever
        from services.llm import LLMFactory, LLMService

        settings = self._settings or get_settings()

        llm_provider = LLMFactory.create(settings)
        llm_service = LLMService(_provider=llm_provider)

        indexer = FAISSIndexer(settings)
        indexer.load_or_build()
        retriever = RAGRetriever(indexer=indexer, settings=settings)

        return Orchestrator(
            detection_agent=IncidentDetectionAgent(),
            rca_agent=RCAAgent(llm=llm_service, retriever=retriever),
            decision_agent=DecisionAgent(),
            remediation_agent=RemediationAgent(llm=llm_service, retriever=retriever),
            validation_agent=ValidationAgent(),
            communication_agent=CommunicationAgent(),
        )
