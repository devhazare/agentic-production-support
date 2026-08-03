"""
core/logging/__init__.py
------------------------
Structured logging setup using structlog.

Pattern: Facade
- Single configure_logging() call at app startup
- All modules use get_logger(__name__) — never print() or bare logging
- JSON output in production, pretty console in development
"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.types import EventDict, WrappedLogger


def add_severity(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    """Map structlog level to GCP/CloudWatch 'severity' key."""
    event_dict["severity"] = event_dict.get("level", method).upper()
    return event_dict


def configure_logging(log_level: str = "INFO", json_logs: bool = False) -> None:
    """
    Configure structlog. Call once at application startup.

    Args:
        log_level: Standard Python log level name.
        json_logs: True in production/staging for machine-parseable output.
    """
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        add_severity,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_logs:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level.upper())


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger for the given module name."""
    return structlog.get_logger(name)
