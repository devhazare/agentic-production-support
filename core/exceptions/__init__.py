"""
core/exceptions/__init__.py
----------------------------
Domain exception hierarchy.

Pattern: Exception hierarchy (OOP inheritance)
- BaseFrameworkError is the root for all domain errors
- Each layer raises its own typed exception
- Never raise bare Exception from domain code
"""

from __future__ import annotations


class BaseFrameworkError(Exception):
    """Root exception for all agentic framework errors."""

    def __init__(self, message: str, context: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict = context or {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, context={self.context})"


# ── Agent layer ────────────────────────────────────────────────────────────

class AgentError(BaseFrameworkError):
    """Base for all agent execution errors."""


class IncidentDetectionError(AgentError):
    """Detection agent failed to parse or score an alert payload."""


class RCAError(AgentError):
    """RCA agent failed — LLM call or context retrieval failure."""


class DecisionError(AgentError):
    """Decision agent could not evaluate severity/confidence."""


class RemediationError(AgentError):
    """Remediation agent step failed."""


class OrchestratorError(AgentError):
    """Pipeline orchestration failure."""


# ── Infrastructure layer ──────────────────────────────────────────────────

class LLMError(BaseFrameworkError):
    """LLM provider returned an error or timed out."""


class LLMConnectionError(LLMError):
    """Could not reach the LLM provider (Ollama not running, etc.)."""


class LLMResponseParseError(LLMError):
    """LLM response could not be parsed into the expected format."""


class EmbeddingError(BaseFrameworkError):
    """Embedding model error."""


class VectorStoreError(BaseFrameworkError):
    """Vector store read/write/index error."""


class VectorStoreNotInitialisedError(VectorStoreError):
    """Vector store has not been built yet."""


# ── Log monitor layer ─────────────────────────────────────────────────────

class LogMonitorError(BaseFrameworkError):
    """Base for log monitoring errors."""


class LogParseError(LogMonitorError):
    """Could not parse a log line in the expected format."""


class LogSourceUnavailableError(LogMonitorError):
    """Log file or stream is not accessible."""


# ── API layer ─────────────────────────────────────────────────────────────

class APIValidationError(BaseFrameworkError):
    """Request payload failed validation."""


class APIRateLimitError(BaseFrameworkError):
    """API rate limit exceeded."""
