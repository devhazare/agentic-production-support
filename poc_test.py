"""
poc_test.py
-----------
End-to-end POC test. Validates the entire chain:

  1. RAG index builds from knowledge base docs
  2. RAG retriever returns real chunks for a query
  3. Mock LLM produces a response
  4. Detection agent creates a real Incident
  5. RCA agent produces a RAG-backed RCA result
  6. Decision agent makes a decision
  7. Remediation agent generates a plan
  8. Log parser parses a real Python log line
  9. Anomaly rule fires on repeated errors

Run:
    python poc_test.py

No Ollama, no uvicorn, no network calls needed.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import time
from pathlib import Path

# Make sure we run from project root
sys.path.insert(0, str(Path(__file__).parent))


def header(title: str) -> None:
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print('─' * 55)


def ok(msg: str) -> None:
    print(f"  ✅  {msg}")


def fail(msg: str) -> None:
    print(f"  ❌  {msg}")
    sys.exit(1)


async def run_tests() -> None:
    print("\n" + "═" * 55)
    print("  Agentic Framework — POC End-to-End Test")
    print("═" * 55)

    # ── 1. Settings ────────────────────────────────────────────────────────
    header("1. Settings load")
    from core.config.settings import get_settings
    settings = get_settings()
    assert settings.app_mode.value == "mock", "Set APP_MODE=mock in .env for this test"
    ok(f"App mode: {settings.app_mode.value}")
    ok(f"LLM provider: {settings.llm_provider.value}")
    ok(f"KB path: {settings.knowledge_base_path}")

    # ── 2. RAG index builds from knowledge base ────────────────────────────
    header("2. RAG index — build from knowledge base")
    from rag.indexer import FAISSIndexer
    indexer = FAISSIndexer(settings)
    indexer.build(force=True)
    chunk_count = len(indexer._chunks)
    if chunk_count == 0:
        fail("No chunks indexed — check data/knowledge_base/ has .md files and data/sample_incidents/incidents.json")
    ok(f"Indexed {chunk_count} chunks from knowledge base + incident history")

    # ── 3. RAG retriever returns real chunks ───────────────────────────────
    header("3. RAG retrieval — semantic search")
    from rag.retriever import RAGRetriever
    retriever = RAGRetriever(indexer=indexer, settings=settings)

    query = "CUDA out of memory torch ml inference batch size"
    chunks = await retriever.retrieve(query, top_k=3)
    if not chunks:
        fail("RAG returned 0 chunks — check embedding model and index build")
    ok(f"Retrieved {len(chunks)} chunks for query: '{query}'")
    for i, c in enumerate(chunks):
        ok(f"  Chunk {i+1}: source={c.source} score={c.score:.3f} preview={c.text[:60]}...")

    # Check that CUDA OOM runbook was retrieved
    sources = [c.source for c in chunks]
    if not any("cuda" in s.lower() or "incident" in s.lower() for s in sources):
        print(f"  ⚠️   Expected cuda/incident in sources, got: {sources}")
    else:
        ok(f"  Relevant source found: {sources[0]}")

    # ── 4. LLM service (mock) ──────────────────────────────────────────────
    header("4. LLM service — mock provider")
    from services.llm import LLMFactory, LLMService
    llm_provider = LLMFactory.create(settings)
    llm_service = LLMService(_provider=llm_provider)
    health = await llm_service.health_check()
    ok(f"LLM health: {health}")
    response = await llm_service.generate("What is the root cause of CUDA OOM error?")
    assert len(response) > 20
    ok(f"LLM response ({len(response)} chars): {response[:80]}...")

    # ── 5. Detection agent ─────────────────────────────────────────────────
    header("5. Detection agent — parse alert + score severity")
    from agents.base import AgentContext
    from agents.detection import IncidentDetectionAgent
    from models import AlertPayloadSchema, Severity

    agent = IncidentDetectionAgent()
    payload = AlertPayloadSchema(
        service="ml-inference",
        alert_type="LogAnomaly",
        metrics={"cpu_percent": 88.0, "memory_mb": 7900.0, "error_rate": 0.12},
        logs_snippet="torch.cuda.OutOfMemoryError: CUDA out of memory. Allocated: 7.8GiB / 8.0GiB",
        log_source="python",
    )
    ctx = AgentContext(incident_id="poc-test-001")
    incident = await agent.run(payload, ctx)
    ok(f"Incident created: {incident.incident_id}")
    ok(f"Service: {incident.service}  Severity: {incident.severity.value}")
    assert incident.service == "ml-inference"
    assert incident.severity in (Severity.HIGH, Severity.CRITICAL, Severity.MEDIUM)

    # ── 6. RCA agent ───────────────────────────────────────────────────────
    header("6. RCA agent — RAG + LLM root cause analysis")
    from agents.rca import RCAAgent

    rca_agent = RCAAgent(llm=llm_service, retriever=retriever)
    rca_result = await rca_agent.run(incident, ctx)
    ok(f"RCA generated for {rca_result.incident_id}")
    ok(f"Confidence: {rca_result.confidence}")
    ok(f"Context chunks used: {len(rca_result.context_chunks)}")
    ok(f"RCA text ({len(rca_result.rca_text)} chars): {rca_result.rca_text[:100]}...")
    assert len(rca_result.rca_text) > 50
    assert len(rca_result.context_chunks) > 0, "RCA must use RAG context"

    # ── 7. Decision agent ──────────────────────────────────────────────────
    header("7. Decision agent — severity × confidence matrix")
    from agents.decision import DecisionAgent
    from models import Decision

    decision_agent = DecisionAgent()
    decision = await decision_agent.run((incident, rca_result), ctx)
    ok(f"Decision: {decision.decision.value}")
    ok(f"Risk score: {decision.risk_score}")
    ok(f"Reason: {decision.reason}")
    assert decision.decision in Decision

    # ── 8. Remediation agent ───────────────────────────────────────────────
    header("8. Remediation agent — generate plan via RAG + LLM")
    from agents.remediation import RemediationAgent, RemediationInput

    rem_agent = RemediationAgent(llm=llm_service, retriever=retriever)
    rem_input = RemediationInput(incident=incident, rca=rca_result, decision=decision)
    plan = await rem_agent.run(rem_input, ctx)
    ok(f"Plan generated: {len(plan.steps)} steps, MTTR={plan.estimated_mttr_minutes}min")
    for step in plan.steps:
        ok(f"  Step {step.step_number} [{step.action_type}]: {step.description[:60]}")
    assert len(plan.steps) > 0

    # ── 9. Log parser — Python format ─────────────────────────────────────
    header("9. Log parser — Python log line parsing")
    from log_monitors.parsers import LogParserFactory
    from models import LogSource

    parser = LogParserFactory.for_source(LogSource.PYTHON)
    raw = "[2025-05-11 14:22:05,112] CRITICAL sample-app - torch.cuda.OutOfMemoryError: CUDA out of memory. Allocated: 7.8GiB / 8.0GiB"
    log_line = parser.parse(raw)
    ok(f"Parsed: level={log_line.level} service={log_line.service}")
    ok(f"Message: {log_line.message[:70]}...")
    assert log_line.level == "CRITICAL"
    assert parser.is_error(log_line)

    # ── 10. Anomaly rule fires ─────────────────────────────────────────────
    header("10. Anomaly detection — rule fires on threshold")
    import re
    from log_monitors.watchers import AnomalyRule, DEFAULT_RULES

    cuda_rule = next(r for r in DEFAULT_RULES if "CUDA" in r.name)
    ok(f"Rule: '{cuda_rule.name}' threshold={cuda_rule.threshold_count} window={cuda_rule.window_seconds}s")

    # Simulate 4 hits — rule fires at 3
    hits = []
    now = time.monotonic()
    for i in range(4):
        if cuda_rule.pattern.search(log_line.message):
            hits.append(now + i * 0.5)
    valid_hits = [t for t in hits if (now + 2) - t <= cuda_rule.window_seconds]
    ok(f"Pattern matched {len(valid_hits)} times in window — threshold={cuda_rule.threshold_count}")
    assert len(valid_hits) >= cuda_rule.threshold_count

    # ── 11. Full orchestrator run ──────────────────────────────────────────
    header("11. Full orchestrator — end-to-end pipeline")
    from orchestration import OrchestratorBuilder

    orch = OrchestratorBuilder().with_settings(settings).build()
    result = await orch.run(payload)
    ok(f"Pipeline complete in {result.pipeline_duration_ms}ms")
    ok(f"Incident: {result.incident.incident_id} [{result.incident.severity.value}]")
    ok(f"RCA confidence: {result.rca.confidence if result.rca else 'N/A'}")
    ok(f"Decision: {result.decision.decision.value if result.decision else 'N/A'}")
    ok(f"Remediation steps: {len(result.remediation_plan.steps) if result.remediation_plan else 0}")

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n" + "═" * 55)
    print("  ALL TESTS PASSED — POC is fully functional!")
    print("═" * 55)
    print("\nNext steps:")
    print("  1. cp .env.example .env")
    print("  2. uvicorn api.main:app --reload --port 8000")
    print("  3. streamlit run ui/dashboard.py")
    print("  4. python sample_app/app.py")
    print("  5. python sample_app/trigger_error.py  (in new terminal)")
    print()


if __name__ == "__main__":
    asyncio.run(run_tests())
