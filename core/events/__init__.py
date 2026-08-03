"""
core/events/__init__.py
-----------------------
Lightweight in-process event bus.

Pattern: Observer / Publish-Subscribe
- Agents publish domain events instead of calling each other directly
- Decouples detection → RCA → decision → remediation chain
- Supports async handlers for non-blocking pipeline steps
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine
from uuid import uuid4

HandlerType = Callable[["DomainEvent"], Coroutine[Any, Any, None]]


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events. Immutable value object."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def event_type(self) -> str:
        return self.__class__.__name__


@dataclass(frozen=True)
class IncidentDetectedEvent(DomainEvent):
    incident_id: str = ""
    service: str = ""
    alert_type: str = ""
    severity: str = ""
    source: str = "metric"  # "metric" | "log"


@dataclass(frozen=True)
class RCACompletedEvent(DomainEvent):
    incident_id: str = ""
    confidence: str = ""
    rca_summary: str = ""


@dataclass(frozen=True)
class DecisionMadeEvent(DomainEvent):
    incident_id: str = ""
    decision: str = ""
    risk_score: float = 0.0


@dataclass(frozen=True)
class RemediationCompletedEvent(DomainEvent):
    incident_id: str = ""
    steps_executed: int = 0
    mttr_minutes: int = 0


@dataclass(frozen=True)
class LogAnomalyDetectedEvent(DomainEvent):
    source: str = ""  # magento | aem | java | python
    pattern: str = ""
    occurrences: int = 0
    service: str = ""
    log_snippet: str = ""


class EventBus:
    """
    In-process async event bus.

    Pattern: Singleton (via module-level instance)
    Usage:
        bus = get_event_bus()
        bus.subscribe(IncidentDetectedEvent, my_handler)
        await bus.publish(IncidentDetectedEvent(incident_id="INC-001", ...))
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[HandlerType]] = defaultdict(list)

    def subscribe(self, event_class: type[DomainEvent], handler: HandlerType) -> None:
        self._handlers[event_class.__name__].append(handler)

    def unsubscribe(self, event_class: type[DomainEvent], handler: HandlerType) -> None:
        self._handlers[event_class.__name__].remove(handler)

    async def publish(self, event: DomainEvent) -> None:
        handlers = self._handlers.get(event.event_type, [])
        if handlers:
            await asyncio.gather(*(h(event) for h in handlers))

    def clear(self) -> None:
        self._handlers.clear()


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return the global singleton EventBus."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
