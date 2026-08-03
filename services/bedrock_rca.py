from __future__ import annotations

import json
import time
from typing import Any

from core.config.settings import Settings
from models import IncidentEvent, KnowledgeDocument, RCAOutput
from services.audit_log import AuditService
from services.observability import get_observability
from utils.security import scrub_sensitive_text


class BedrockRCAClient:
    def __init__(self, settings: Settings, audit: AuditService) -> None:
        self.settings = settings
        self.audit = audit
        self._client = None
        if settings.use_aws:
            import boto3

            self._client = boto3.client("bedrock-runtime", region_name=settings.aws_region)

    def generate_rca(self, event: IncidentEvent, docs: list[KnowledgeDocument]) -> RCAOutput:
        started = time.perf_counter()
        prompt = self._build_prompt(event, docs)
        self.audit.record(
            "bedrock_model_call_requested",
            event.incident_id,
            model_id=self.settings.bedrock_model_id,
            citations=[doc.source_uri for doc in docs],
        )
        if not self._client:
            output = self._mock_rca(event, docs)
            response_text = output.model_dump_json()
        else:
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": self.settings.bedrock_max_tokens,
                "temperature": self.settings.bedrock_temperature,
                "system": "You are an SRE RCA assistant. Return only valid JSON.",
                "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            }
            response = self._client.invoke_model(
                modelId=self.settings.bedrock_model_id,
                body=json.dumps(body),
                accept="application/json",
                contentType="application/json",
            )
            payload = json.loads(response["body"].read())
            text = payload["content"][0]["text"]
            output = self._parse_rca_output(text)
            response_text = text
        duration_ms = int((time.perf_counter() - started) * 1000)
        get_observability().record_llm_usage(
            provider="bedrock",
            model=self.settings.bedrock_model_id,
            prompt=prompt,
            response=response_text,
            duration_ms=duration_ms,
            status="success",
        )
        self.audit.record(
            "bedrock_model_call_completed",
            event.incident_id,
            confidence_score=output.confidence_score,
            risk_level=output.risk_level,
        )
        return output

    def _build_prompt(self, event: IncidentEvent, docs: list[KnowledgeDocument]) -> str:
        context = "\n\n".join(
            f"Source: {doc.source_uri}\nTitle: {doc.title}\n{scrub_sensitive_text(doc.text)}"
            for doc in docs
        )
        incident = scrub_sensitive_text(event.model_dump_json())
        return f"""
Return JSON with keys: probable_root_cause, supporting_evidence,
similar_incident_references, recommended_action, recommended_action_type,
confidence_score, risk_level, citations.
Use only retrieved context. Cite source_uri values.

Incident:
{incident}

Retrieved context:
{context}
"""

    def _parse_rca_output(self, text: str) -> RCAOutput:
        raw = text.strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw.removeprefix("json").strip()
        payload = json.loads(raw)

        for key in ("supporting_evidence", "similar_incident_references", "citations"):
            value = payload.get(key, [])
            if isinstance(value, str):
                payload[key] = [value]
            elif isinstance(value, list):
                payload[key] = [
                    json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
                    for item in value
                ]
            else:
                payload[key] = [str(value)]

        for key in ("probable_root_cause", "recommended_action"):
            value = payload.get(key, "")
            if isinstance(value, list):
                payload[key] = " ".join(
                    json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
                    for item in value
                )
            elif not isinstance(value, str):
                payload[key] = str(value)

        if "risk_level" in payload and isinstance(payload["risk_level"], str):
            payload["risk_level"] = payload["risk_level"].lower()

        return RCAOutput.model_validate(payload)

    def _mock_rca(self, event: IncidentEvent, docs: list[KnowledgeDocument]) -> RCAOutput:
        text = f"{event.alert_type} {event.metric_name} {event.logs_summary}".lower()
        action = "restart_service_mock"
        cause = "Service instability indicated by logs and metric anomaly."
        risk = "medium"
        confidence = 0.8
        if "connection" in text or "database" in text:
            cause = "Database connection pool exhaustion is limiting request throughput."
            action = "scale_service_mock"
            confidence = 0.88
        elif "queue" in text or "sqs" in text or "backlog" in text:
            cause = "Consumer throughput is below producer rate, causing queue backlog."
            action = "drain_queue_mock"
            confidence = 0.9
        elif "deployment" in text or "rollback" in text:
            cause = "Recent deployment likely introduced a regression."
            action = "rollback_deployment_mock"
            risk = "high"
            confidence = 0.86
        elif "restart" in text or "task" in text:
            cause = "Task restart loop points to health check or runtime failure."
            action = "restart_service_mock"
            confidence = 0.83
        if event.severity.value in {"High", "Critical"}:
            risk = "high"
        citations = [doc.source_uri for doc in docs[:5]]
        return RCAOutput(
            probable_root_cause=cause,
            supporting_evidence=[
                f"{event.metric_name}={event.metric_value}",
                scrub_sensitive_text(event.logs_summary)[:300],
            ],
            similar_incident_references=[doc.title for doc in docs if doc.doc_type == "rca"][:3],
            recommended_action=f"Run {action} as a dry-run MVP remediation after policy checks.",
            recommended_action_type=action,
            confidence_score=confidence if docs else 0.55,
            risk_level=risk,  # type: ignore[arg-type]
            citations=citations,
        )
