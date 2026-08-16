from __future__ import annotations

import pytest

from core.config.settings import Settings
from services.llm import LLMProviderProtocol, LLMService
from services.model_egress import sanitize_for_embedding, sanitize_for_model


def test_sanitize_for_model_redacts_pii_infra_paths_and_capacity() -> None:
    settings = Settings(
        model_egress_redaction_token="[X]",
        model_egress_fail_closed=True,
    )
    text = (
        "arn:aws:lambda:us-east-1:123456789012:function:ai-ops-mvp-dev-api "
        "failed at /Users/superadmin/project/services/bedrock_rca.py "
        "with memory_size=1024 MB. Contact user@example.com from 10.0.0.12."
    )

    result = sanitize_for_model(text, settings=settings)

    assert "arn:aws" not in result.text
    assert "123456789012" not in result.text
    assert "/Users/superadmin" not in result.text
    assert "1024 MB" not in result.text
    assert "user@example.com" not in result.text
    assert "10.0.0.12" not in result.text
    assert result.was_modified


def test_sanitize_for_embedding_redacts_secret_material() -> None:
    settings = Settings(model_egress_redaction_token="[X]")
    result = sanitize_for_embedding(
        "postgres://admin:secret@internal.db.local/app password=supersecret",
        settings=settings,
    )

    assert "postgres://" not in result.text
    assert "supersecret" not in result.text
    assert result.was_modified


class CapturingProvider(LLMProviderProtocol):
    def __init__(self) -> None:
        self.prompt = ""

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.1,
        max_tokens: int = 1000,
    ) -> str:
        self.prompt = prompt
        return "ok"

    async def health_check(self) -> dict[str, object]:
        return {"status": "ok"}


@pytest.mark.asyncio
async def test_llm_service_sanitizes_prompt_before_provider_call() -> None:
    provider = CapturingProvider()
    service = LLMService(provider)

    await service.generate(
        "Use /Users/superadmin/project/app.py and token=abc123 for ai-ops-mvp-dev-api",
    )

    assert "/Users/superadmin" not in provider.prompt
    assert "abc123" not in provider.prompt
    assert "ai-ops-mvp-dev-api" not in provider.prompt
    assert "[MODEL_REDACTED]" in provider.prompt
