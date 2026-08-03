"""
log_monitors/parsers/__init__.py
---------------------------------
Log line parsers for each application type.

Pattern: Strategy — each parser implements LogParser protocol.
         Factory — LogParserFactory.for_source() picks the right one.
"""

from __future__ import annotations

import abc
import re
from datetime import datetime, timezone

from core.exceptions import LogParseError
from models import LogLine, LogSource

# ── Parser interface ──────────────────────────────────────────────────────────

class LogParser(abc.ABC):
    @abc.abstractmethod
    def parse(self, raw_line: str) -> LogLine:
        """Parse a raw log line into a structured LogLine. Raises LogParseError on failure."""

    @abc.abstractmethod
    def is_error(self, line: LogLine) -> bool:
        """Return True if this log line represents an error/warning."""


# ── Concrete parsers ──────────────────────────────────────────────────────────

_TS = datetime.now(timezone.utc).isoformat()


class MagentoLogParser(LogParser):
    """
    Parses Magento 2 exception.log format:
    [YYYY-MM-DD HH:MM:SS] main.ERROR: Message {"context"} []
    """

    _PATTERN = re.compile(
        r"\[(?P<ts>[^\]]+)\]\s+(?:main\.)?(?P<level>DEBUG|INFO|NOTICE|WARNING|ERROR|CRITICAL|ALERT|EMERGENCY):\s*(?P<msg>.*)",
        re.IGNORECASE,
    )
    _ERROR_LEVELS = {"ERROR", "CRITICAL", "ALERT", "EMERGENCY"}

    def parse(self, raw_line: str) -> LogLine:
        m = self._PATTERN.match(raw_line.strip())
        if not m:
            raise LogParseError(f"Magento log parse failed: {raw_line[:80]}")
        return LogLine(
            source=LogSource.MAGENTO,
            level=m.group("level").upper(),
            message=m.group("msg"),
            raw=raw_line,
            timestamp=m.group("ts"),
        )

    def is_error(self, line: LogLine) -> bool:
        return line.level in self._ERROR_LEVELS


class AEMLogParser(LogParser):
    """
    Parses AEM (Adobe Experience Manager) error.log format:
    DD.MM.YYYY HH:MM:SS.mmm *LEVEL* [thread] class Message
    """

    _PATTERN = re.compile(
        r"(?P<ts>\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+\*(?P<level>DEBUG|INFO|WARN|ERROR)\*\s+(?P<msg>.*)",
        re.IGNORECASE,
    )
    _ERROR_LEVELS = {"ERROR", "WARN"}

    def parse(self, raw_line: str) -> LogLine:
        m = self._PATTERN.match(raw_line.strip())
        if not m:
            raise LogParseError(f"AEM log parse failed: {raw_line[:80]}")
        return LogLine(
            source=LogSource.AEM,
            level=m.group("level").upper(),
            message=m.group("msg"),
            raw=raw_line,
            timestamp=m.group("ts"),
        )

    def is_error(self, line: LogLine) -> bool:
        return line.level in self._ERROR_LEVELS


class JavaLogParser(LogParser):
    """
    Parses SLF4J/Logback format:
    YYYY-MM-DD HH:MM:SS.mmm LEVEL [service,traceId] class - Message
    """

    _PATTERN = re.compile(
        r"(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+"
        r"(?P<level>TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\s+"
        r"(?:\[(?P<service>[^,\]]*),?(?P<trace>[^\]]*)\]\s+)?"
        r"(?P<class>[\w$.]+)\s+-\s+(?P<msg>.*)",
        re.IGNORECASE,
    )
    _ERROR_LEVELS = {"ERROR", "FATAL", "WARN"}

    def parse(self, raw_line: str) -> LogLine:
        m = self._PATTERN.match(raw_line.strip())
        if not m:
            raise LogParseError(f"Java log parse failed: {raw_line[:80]}")
        return LogLine(
            source=LogSource.JAVA,
            level=m.group("level").upper(),
            message=m.group("msg"),
            raw=raw_line,
            timestamp=m.group("ts"),
            service=m.group("service") or "",
            trace_id=m.group("trace") or "",
        )

    def is_error(self, line: LogLine) -> bool:
        return line.level in self._ERROR_LEVELS


class PythonLogParser(LogParser):
    """
    Parses Python logging module format:
    [YYYY-MM-DD HH:MM:SS,mmm] LEVEL logger - Message
    """

    _PATTERN = re.compile(
        r"\[(?P<ts>[^\]]+)\]\s+(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
        r"(?P<logger>[\w\-.]+)\s+-\s+(?P<msg>.*)",
        re.IGNORECASE,
    )
    _ERROR_LEVELS = {"ERROR", "CRITICAL", "WARNING"}

    def parse(self, raw_line: str) -> LogLine:
        m = self._PATTERN.match(raw_line.strip())
        if not m:
            raise LogParseError(f"Python log parse failed: {raw_line[:80]}")
        return LogLine(
            source=LogSource.PYTHON,
            level=m.group("level").upper(),
            message=m.group("msg"),
            raw=raw_line,
            timestamp=m.group("ts"),
            service=m.group("logger"),
        )

    def is_error(self, line: LogLine) -> bool:
        return line.level in self._ERROR_LEVELS


# ── Factory ───────────────────────────────────────────────────────────────────

_PARSERS: dict[LogSource, LogParser] = {
    LogSource.MAGENTO: MagentoLogParser(),
    LogSource.AEM: AEMLogParser(),
    LogSource.JAVA: JavaLogParser(),
    LogSource.PYTHON: PythonLogParser(),
}


class LogParserFactory:
    @staticmethod
    def for_source(source: LogSource) -> LogParser:
        parser = _PARSERS.get(source)
        if parser is None:
            raise LogParseError(f"No parser registered for source: {source}")
        return parser
