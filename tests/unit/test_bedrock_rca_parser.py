from __future__ import annotations

import json
from pathlib import Path

from core.config.settings import Settings
from services.audit_log import AuditService
from services.bedrock_rca import BedrockRCAClient


def test_parse_rca_output_coerces_recommended_action_list(tmp_path: Path) -> None:
    settings = Settings(local_audit_path=tmp_path / "audit.jsonl")
    client = BedrockRCAClient(settings, AuditService(settings))
    output = client._parse_rca_output(
        json.dumps(
            {
                "probable_root_cause": "database connection contention",
                "supporting_evidence": ["p99_latency_ms=4200"],
                "similar_incident_references": [],
                "recommended_action": [
                    "Confirm latency concentration in checkout.",
                    "Review DB pool saturation and lock waits.",
                    "Use retrieved runbook as primary evidence.",
                ],
                "recommended_action_type": "scale_service_mock",
                "confidence_score": 0.9,
                "risk_level": "High",
                "citations": ["s3://runbook"],
            }
        )
    )

    assert isinstance(output.recommended_action, str)
    assert "Confirm latency concentration" in output.recommended_action
    assert output.risk_level == "high"
