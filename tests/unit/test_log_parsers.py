"""tests/unit/test_log_parsers.py — unit tests for each log parser."""

from __future__ import annotations

import pytest

from log_monitors.parsers import (
    AEMLogParser,
    JavaLogParser,
    LogParserFactory,
    MagentoLogParser,
    PythonLogParser,
)
from models import LogSource


class TestMagentoParser:
    def setup_method(self):
        self.p = MagentoLogParser()

    def test_parses_error_line(self):
        raw = "[2025-05-09 14:22:11] main.ERROR: SQLSTATE[HY000]: Lock wait timeout {}"
        line = self.p.parse(raw)
        assert line.level == "ERROR"
        assert "SQLSTATE" in line.message
        assert line.source == LogSource.MAGENTO

    def test_is_error_for_critical(self):
        raw = "[2025-05-09 14:22:11] main.CRITICAL: Memory limit reached {}"
        line = self.p.parse(raw)
        assert self.p.is_error(line) is True

    def test_is_not_error_for_info(self):
        raw = "[2025-05-09 14:22:11] main.INFO: Order placed {}"
        line = self.p.parse(raw)
        assert self.p.is_error(line) is False


class TestJavaParser:
    def setup_method(self):
        self.p = JavaLogParser()

    def test_parses_with_trace_id(self):
        raw = "2025-05-09 14:21:58.112 ERROR [user-service,f9e8d7c6] c.e.u.SessionManager - OOM: heap"
        line = self.p.parse(raw)
        assert line.level == "ERROR"
        assert line.service == "user-service"
        assert line.trace_id == "f9e8d7c6"

    def test_is_error_for_fatal(self):
        raw = "2025-05-09 14:20:30.559 FATAL [payment-service,ff778899] c.e.p.CB - Circuit OPEN"
        line = self.p.parse(raw)
        assert self.p.is_error(line) is True


class TestLogParserFactory:
    def test_returns_correct_parser_for_source(self):
        p = LogParserFactory.for_source(LogSource.MAGENTO)
        assert isinstance(p, MagentoLogParser)

    def test_raises_for_unknown_source(self):
        from core.exceptions import LogParseError
        with pytest.raises(LogParseError):
            LogParserFactory.for_source(LogSource.CLOUDWATCH)  # type: ignore[arg-type]
