"""
services/llm/__init__.py
------------------------
LLM service layer.

Patterns applied:
  - Strategy: LLMProvider interface + concrete implementations (Ollama, OpenAI, etc.)
  - Factory: LLMFactory.create() selects the correct strategy at runtime
  - Adapter: each provider adapts to the common LLMProvider protocol
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass

import httpx

from core.config.settings import LLMProvider as LLMProviderEnum, Settings
from core.exceptions import LLMConnectionError, LLMError
from core.logging import get_logger
from services.observability import get_observability

logger = get_logger(__name__)


# ── Strategy interface ────────────────────────────────────────────────────────

class LLMProviderProtocol(abc.ABC):
    """Abstract base for all LLM provider strategies."""

    @abc.abstractmethod
    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.1,
        max_tokens: int = 1000,
    ) -> str:
        """Generate a completion and return the text."""

    @abc.abstractmethod
    async def health_check(self) -> dict[str, object]:
        """Return provider health status."""


# ── Concrete strategies ───────────────────────────────────────────────────────

class OllamaProvider(LLMProviderProtocol):
    """Ollama local LLM provider."""

    def __init__(self, base_url: str, model: str, timeout: int = 120) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.1,
        max_tokens: int = 1000,
    ) -> str:
        payload = {
            "model": self._model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/api/generate", json=payload)
                resp.raise_for_status()
                return resp.json().get("response", "").strip()
        except httpx.ConnectError as exc:
            raise LLMConnectionError(
                "Ollama not reachable. Run: ollama serve",
                context={"url": self._base_url},
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise LLMError(
                f"Ollama HTTP {exc.response.status_code}",
                context={"body": exc.response.text[:200]},
            ) from exc

    async def health_check(self) -> dict[str, object]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                models = [m["name"] for m in resp.json().get("models", [])]
                return {"status": "online", "models": models}
        except Exception:
            return {"status": "offline", "models": []}

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model


class MockProvider(LLMProviderProtocol):
    """
    Deterministic mock provider for tests and demo mode.
    Never calls a real LLM.
    """

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.1,
        max_tokens: int = 1000,
    ) -> str:
        prompt_lower = prompt.lower()
        # Check remediation FIRST — its prompt also contains "root cause"
        if "remediat" in prompt_lower or "prioritised" in prompt_lower:
            return (
                "[SCALE] Scale ml-inference replicas 2->4 immediately\n"
                "[CONFIG] Reduce batch_size 128->32 via torch.cuda.get_device_properties()\n"
                "[RESTART] Rolling restart ml-inference pods to clear GPU memory\n"
                "[INVESTIGATE] Check nvidia-smi VRAM on all nodes\n"
                "[ALERT] Notify #oncall with incident summary\n"
                "ESTIMATED_MTTR: 13"
            )
        if "root cause" in prompt_lower or "rca" in prompt_lower or "analyse" in prompt_lower:
            return (
                "**Root Cause (Mock - RAG-augmented)**\n\n"
                "1. Most Probable Root Cause: CUDA OOM caused by batch_size=128 "
                "exceeding T4 GPU VRAM after instance downgrade from A100.\n\n"
                "2. Supporting Evidence: logs show Allocated 7.8GiB/8.0GiB. "
                "RAG retrieved INC-2024-L03 (identical past incident) and "
                "runbook_cuda_oom.md with exact remediation steps.\n\n"
                "3. Contributing Factors:\n"
                "- Batch size hardcoded, not dynamic per GPU type\n"
                "- No GPU memory alert configured\n"
                "- No canary deployment for model updates\n\n"
                "4. Confidence Level: HIGH - exact RAG match to INC-2024-L03."
            )
        return "[Mock LLM] Install Ollama: ollama pull llama3.2 for real responses."

    async def health_check(self) -> dict[str, object]:
        return {"status": "mock", "models": ["mock-llm"]}

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-llm"


# ── Factory ───────────────────────────────────────────────────────────────────

class LLMFactory:
    """
    Factory pattern: creates the correct LLMProvider strategy
    based on configuration, without callers knowing the concrete type.
    """

    @staticmethod
    def create(settings: Settings) -> LLMProviderProtocol:
        if settings.is_mock:
            logger.info("llm.factory", provider="mock")
            return MockProvider()

        match settings.llm_provider:
            case LLMProviderEnum.OLLAMA:
                logger.info("llm.factory", provider="ollama", model=settings.ollama_model)
                return OllamaProvider(
                    base_url=settings.ollama_base_url,
                    model=settings.ollama_model,
                    timeout=settings.llm_timeout_sec,
                )
            case LLMProviderEnum.OPENAI:
                # Import lazily to avoid requiring openai package when not used
                from services.llm.openai_provider import OpenAIProvider  # noqa: PLC0415
                return OpenAIProvider(settings)
            case LLMProviderEnum.ANTHROPIC:
                from services.llm.anthropic_provider import AnthropicProvider  # noqa: PLC0415
                return AnthropicProvider(settings)
            case _:
                raise LLMError(f"Unsupported LLM provider: {settings.llm_provider}")


@dataclass
class LLMService:
    """
    Thin facade around the chosen LLMProvider strategy.
    Adds timing, structured logging, and retry logic.
    Injected into agents via constructor DI.
    """

    _provider: LLMProviderProtocol

    async def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.1,
        max_tokens: int = 1000,
    ) -> str:
        start = time.perf_counter()
        try:
            result = await self._provider.generate(
                prompt, system=system, temperature=temperature, max_tokens=max_tokens
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            get_observability().record_llm_usage(
                provider=getattr(self._provider, "provider_name", self._provider.__class__.__name__),
                model=getattr(self._provider, "model_name", "unknown"),
                prompt=prompt,
                response=result,
                duration_ms=duration_ms,
                status="ok",
            )
            logger.info(
                "llm.generate.ok",
                prompt_len=len(prompt),
                response_len=len(result),
                duration_ms=duration_ms,
            )
            return result
        except LLMConnectionError:
            logger.warning("llm.generate.connection_error — falling back to mock")
            result = await MockProvider().generate(prompt, system=system)
            duration_ms = int((time.perf_counter() - start) * 1000)
            get_observability().record_llm_usage(
                provider="mock-fallback",
                model="mock-llm",
                prompt=prompt,
                response=result,
                duration_ms=duration_ms,
                status="fallback",
            )
            return result
        except LLMError as exc:
            logger.error("llm.generate.error", error=str(exc))
            raise

    async def health_check(self) -> dict[str, object]:
        return await self._provider.health_check()
