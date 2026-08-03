"""
agents/rca/__init__.py
-----------------------
Root Cause Analysis Agent.

Patterns: Template Method, Dependency Injection (LLMService + RAGRetriever),
          Prompt Builder (separate class, Single Responsibility).
"""

from __future__ import annotations

from agents.base import AgentContext, BaseAgent
from core.events import RCACompletedEvent, get_event_bus
from core.exceptions import RCAError
from models import ContextChunk, Incident, RCAResult
from rag.retriever import RAGRetriever
from services.llm import LLMService

SYSTEM_PROMPT = """\
You are a senior SRE specialising in root cause analysis for distributed systems,
cloud infrastructure (AWS, Kubernetes), Magento, AEM, Java microservices, and Python
ML pipelines. Given an incident report and relevant runbook/incident-history context,
produce a concise, actionable RCA.

Always respond with this structure:
1. Most Probable Root Cause — one sentence
2. Supporting Evidence — from metrics and logs
3. Contributing Factors — secondary conditions
4. Confidence Level — LOW / MEDIUM / HIGH with one-line justification
"""


class PromptBuilder:
    """
    Single Responsibility: builds LLM prompts from structured data.
    Keeps prompt engineering separated from agent logic.
    """

    @staticmethod
    def rca_prompt(incident: Incident, context_text: str) -> str:
        return (
            f"## Incident\n{incident.summary()}\n\n"
            f"## Retrieved Context\n{context_text}\n\n"
            f"## Task\n"
            "Analyse the incident and produce a root cause analysis following "
            "the structure defined in your system prompt."
        )

    @staticmethod
    def remediation_prompt(
        incident: Incident, rca_text: str, context_text: str
    ) -> str:
        return (
            f"## Incident\n{incident.summary()}\n\n"
            f"## Root Cause Analysis\n{rca_text}\n\n"
            f"## Runbook Context\n{context_text}\n\n"
            f"## Task\n"
            "Generate a prioritised remediation plan with 3–6 steps. "
            "Prefix each step with one of: [SCALE] [RESTART] [ROLLBACK] "
            "[CONFIG] [ALERT] [INVESTIGATE]. "
            "End with: ESTIMATED_MTTR: <N>"
        )


def _extract_confidence(text: str) -> str:
    for level in ("HIGH", "MEDIUM", "LOW"):
        if level in text.upper():
            return level
    return "MEDIUM"


class RCAAgent(BaseAgent[Incident, RCAResult]):
    """
    Generates root cause analysis using RAG-augmented LLM calls.

    DI contract: LLMService and RAGRetriever injected — never instantiated here.
    This keeps the agent testable with mock dependencies.
    """

    def __init__(self, llm: LLMService, retriever: RAGRetriever) -> None:
        super().__init__()
        self._llm = llm
        self._retriever = retriever
        self._bus = get_event_bus()
        self._prompt_builder = PromptBuilder()

    async def _execute(
        self, incident: Incident, context: AgentContext
    ) -> RCAResult:
        query = f"{incident.alert_type} {incident.service} {incident.logs_snippet[:200]}"
        chunks: list[ContextChunk] = await self._retriever.retrieve(query, top_k=4)

        context_text = self._format_context(chunks)
        prompt = self._prompt_builder.rca_prompt(incident, context_text)

        rca_text = await self._llm.generate(
            prompt=prompt,
            system=SYSTEM_PROMPT,
            temperature=0.1,
        )

        if not rca_text:
            raise RCAError(
                "LLM returned empty RCA response",
                context={"incident_id": incident.incident_id},
            )

        confidence = _extract_confidence(rca_text)
        result = RCAResult(
            incident_id=incident.incident_id,
            rca_text=rca_text,
            confidence=confidence,
            context_chunks=chunks,
        )

        context.set("rca_result", result)
        self._logger.info(
            "rca.complete",
            incident_id=incident.incident_id,
            confidence=confidence,
            chunks_used=len(chunks),
        )
        return result

    async def _post_execute(
        self, result: RCAResult, context: AgentContext
    ) -> None:
        await self._bus.publish(
            RCACompletedEvent(
                incident_id=result.incident_id,
                confidence=result.confidence,
                rca_summary=result.rca_text[:300],
            )
        )

    @staticmethod
    def _format_context(chunks: list[ContextChunk]) -> str:
        if not chunks:
            return "No relevant context found."
        parts = [
            f"[Source {i + 1}: {c.source} | score={c.score:.2f}]\n{c.text}"
            for i, c in enumerate(chunks)
        ]
        return "\n\n---\n\n".join(parts)
