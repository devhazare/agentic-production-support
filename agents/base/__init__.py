"""
agents/base/__init__.py
-----------------------
Abstract base agent.

Patterns applied:
  - Template Method: BaseAgent.run() defines the skeleton algorithm;
    subclasses override _execute() with concrete logic.
  - Hook methods: _pre_execute() and _post_execute() for cross-cutting concerns.
  - DI: dependencies injected via __init__, not instantiated inside the class.
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from core.exceptions import AgentError
from core.logging import get_logger

logger = get_logger(__name__)

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


@dataclass
class AgentContext:
    """
    Shared context passed between agents in a pipeline run.
    Pattern: Context Object — carries cross-cutting state without coupling agents.
    """

    incident_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.metadata[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.metadata.get(key, default)


class BaseAgent(abc.ABC, Generic[InputT, OutputT]):
    """
    Abstract base for all framework agents.

    Template Method pattern:
        run(input, context) → calls _pre_execute → _execute → _post_execute
        Concrete agents implement only _execute().

    Lifecycle hooks:
        _pre_execute()  — validate / set up (default: no-op)
        _execute()      — MUST override
        _post_execute() — cleanup / emit events (default: no-op)
    """

    def __init__(self) -> None:
        self.name: str = self.__class__.__name__
        self._logger = get_logger(f"agent.{self.name.lower()}")

    async def run(self, input_data: InputT, context: AgentContext) -> OutputT:
        """
        Template method — do not override.
        Provides consistent timing, logging, and error handling for every agent.
        """
        start = time.perf_counter()
        self._logger.info(
            "agent.start",
            agent=self.name,
            incident_id=context.incident_id,
        )
        try:
            from services.observability import get_observability  # noqa: PLC0415

            get_observability().record_agent_start(self.name, context.incident_id)
        except Exception:
            pass

        try:
            await self._pre_execute(input_data, context)
            result = await self._execute(input_data, context)
            await self._post_execute(result, context)
            duration_ms = int((time.perf_counter() - start) * 1000)
            self._logger.info(
                "agent.done",
                agent=self.name,
                incident_id=context.incident_id,
                duration_ms=duration_ms,
            )
            try:
                from services.observability import get_observability  # noqa: PLC0415

                get_observability().record_agent_done(
                    self.name, context.incident_id, duration_ms
                )
            except Exception:
                pass
            return result

        except AgentError:
            raise
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            self._logger.error(
                "agent.error",
                agent=self.name,
                incident_id=context.incident_id,
                error=str(exc),
                duration_ms=duration_ms,
            )
            try:
                from services.observability import get_observability  # noqa: PLC0415

                get_observability().record_agent_error(
                    self.name, context.incident_id, duration_ms, str(exc)
                )
            except Exception:
                pass
            raise AgentError(
                f"{self.name} failed: {exc}",
                context={"incident_id": context.incident_id},
            ) from exc

    @abc.abstractmethod
    async def _execute(self, input_data: InputT, context: AgentContext) -> OutputT:
        """Core agent logic. Must be implemented by every concrete agent."""

    async def _pre_execute(self, input_data: InputT, context: AgentContext) -> None:
        """Hook: called before _execute. Override for validation / setup."""

    async def _post_execute(self, result: OutputT, context: AgentContext) -> None:
        """Hook: called after _execute. Override for events / cleanup."""
