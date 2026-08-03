"""
log_monitors/watchers/__init__.py
----------------------------------
Log file tail watcher + pattern-based anomaly detection.

Pattern: Observer — LogWatcher emits LogAnomalyDetectedEvents via EventBus.
         Composite — MultiSourceWatcher aggregates multiple LogWatchers.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from core.events import LogAnomalyDetectedEvent, get_event_bus
from core.exceptions import LogSourceUnavailableError
from core.logging import get_logger
from log_monitors.parsers import LogParserFactory
from models import LogLine, LogSource

logger = get_logger(__name__)


@dataclass(frozen=True)
class AnomalyRule:
    name: str
    pattern: re.Pattern
    threshold_count: int
    window_seconds: int
    min_severity: str = "HIGH"


# ── Default anomaly detection rules ──────────────────────────────────────────

DEFAULT_RULES: list[AnomalyRule] = [
    AnomalyRule("OOM / heap exhaustion",    re.compile(r"OutOfMemoryError|Java heap space|GC overhead"), 5, 300),
    AnomalyRule("DB connection exhaustion", re.compile(r"Connection is not available|pool.*timeout", re.I), 5, 300),
    AnomalyRule("Magento DB deadlock",      re.compile(r"SQLSTATE.*Lock wait timeout", re.I), 10, 600),
    AnomalyRule("Circuit breaker open",     re.compile(r"Circuit OPEN|failing fast", re.I), 3, 120),
    AnomalyRule("CUDA OOM",                 re.compile(r"torch\.cuda\.OutOfMemoryError", re.I), 3, 600),
    AnomalyRule("PHP memory limit",         re.compile(r"Memory limit reached|memory_limit", re.I), 3, 300),
    AnomalyRule("AEM workflow failure",     re.compile(r"WorkflowException.*Step failed", re.I), 3, 300),
    AnomalyRule("Error rate spike",         re.compile(r"^(ERROR|FATAL|CRITICAL)$", re.I), 20, 300),
]


class LogWatcher:
    """
    Tails a single log file, parses each line, and fires anomaly events
    when a detection rule threshold is crossed within its time window.
    """

    def __init__(
        self,
        source: LogSource,
        path: str,
        rules: list[AnomalyRule] | None = None,
        poll_interval_sec: int = 5,
    ) -> None:
        self._source = source
        self._path = Path(path)
        self._rules = rules or DEFAULT_RULES
        self._poll_interval = poll_interval_sec
        self._bus = get_event_bus()
        self._parser = LogParserFactory.for_source(source)
        self._running = False
        self._window_counts: dict[str, list[float]] = {r.name: [] for r in self._rules}

    async def start(self) -> None:
        if not self._path.exists():
            logger.warning(
                "log_watcher.path_missing",
                source=self._source.value,
                path=str(self._path),
            )
            # In mock/dev mode we just return instead of raising
            return

        self._running = True
        logger.info("log_watcher.start", source=self._source.value, path=str(self._path))
        try:
            await self._tail()
        except asyncio.CancelledError:
            self._running = False

    def stop(self) -> None:
        self._running = False

    async def _tail(self) -> None:
        try:
            with self._path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(0, 2)  # seek to end
                while self._running:
                    line = f.readline()
                    if line:
                        await self._process_line(line)
                    else:
                        await asyncio.sleep(self._poll_interval)
        except OSError as exc:
            raise LogSourceUnavailableError(
                f"Cannot read log: {self._path}", context={"error": str(exc)}
            ) from exc

    async def _process_line(self, raw: str) -> None:
        import time

        try:
            log_line = self._parser.parse(raw)
        except Exception:
            return  # skip unparseable lines silently

        now = time.monotonic()
        for rule in self._rules:
            # Check pattern against the message text
            matched = rule.pattern.search(log_line.message)

            # Special case: "Error rate spike" counts any error-level line
            if not matched and rule.name == "Error rate spike":
                matched = self._parser.is_error(log_line)

            if matched:
                bucket = self._window_counts[rule.name]
                bucket.append(now)
                # evict entries outside the time window
                self._window_counts[rule.name] = [
                    t for t in bucket if now - t <= rule.window_seconds
                ]
                count = len(self._window_counts[rule.name])
                if count >= rule.threshold_count:
                    await self._fire_anomaly(rule, log_line, count)
                    self._window_counts[rule.name] = []  # reset after firing

    async def _fire_anomaly(
        self, rule: AnomalyRule, line: LogLine, count: int
    ) -> None:
        logger.warning(
            "log_watcher.anomaly",
            source=self._source.value,
            rule=rule.name,
            count=count,
        )
        await self._bus.publish(
            LogAnomalyDetectedEvent(
                source=self._source.value,
                pattern=rule.name,
                occurrences=count,
                service=line.service or self._source.value,
                log_snippet=line.raw[:300],
            )
        )


MagentoLogKind = Literal["exception", "system", "access"]


@dataclass(frozen=True)
class MagentoLogEvent:
    kind: MagentoLogKind
    raw: str
    is_failure: bool
    failure_reason: str


class MagentoCorrelatedLogWatcher:
    """
    Tails Magento exception.log, system.log, and access.log together.

    When enough failures occur in the configured rolling window, it emits one
    LogAnomalyDetectedEvent with recent evidence from all three files. The
    orchestrator then runs the incident through RAG-backed RCA and decisioning.
    """

    _ACCESS_RE = re.compile(r'"(?P<method>[A-Z]+)\s+(?P<path>\S+)\s+HTTP/[0-9.]+"\s+(?P<status>\d{3})')
    _MAGENTO_LEVEL_RE = re.compile(r"main\.(?P<level>WARNING|ERROR|CRITICAL|ALERT|EMERGENCY):", re.I)

    def __init__(
        self,
        exception_log_path: str,
        system_log_path: str,
        access_log_path: str,
        threshold_count: int = 5,
        window_seconds: int = 300,
        cooldown_seconds: int = 60,
        poll_interval_sec: int = 5,
    ) -> None:
        self._paths: dict[MagentoLogKind, Path] = {
            "exception": Path(exception_log_path),
            "system": Path(system_log_path),
            "access": Path(access_log_path),
        }
        self._threshold_count = threshold_count
        self._window_seconds = window_seconds
        self._cooldown_seconds = cooldown_seconds
        self._poll_interval = poll_interval_sec
        self._bus = get_event_bus()
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._failure_times: list[float] = []
        self._recent: list[MagentoLogEvent] = []
        self._last_fired_at = 0.0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        missing = [f"{kind}={path}" for kind, path in self._paths.items() if not path.exists()]
        if missing:
            logger.warning("magento_correlated_watcher.paths_missing", missing=missing)
            return

        self._running = True
        self._tasks = [
            asyncio.create_task(self._tail(kind, path), name=f"magento-{kind}-watcher")
            for kind, path in self._paths.items()
        ]
        logger.info(
            "magento_correlated_watcher.start",
            threshold=self._threshold_count,
            window_seconds=self._window_seconds,
            cooldown_seconds=self._cooldown_seconds,
            paths={kind: str(path) for kind, path in self._paths.items()},
        )
        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            self.stop()
            raise

    def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()

    async def _tail(self, kind: MagentoLogKind, path: Path) -> None:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(0, 2)
                while self._running:
                    line = f.readline()
                    if line:
                        await self._process_line(kind, line.strip())
                    else:
                        await asyncio.sleep(self._poll_interval)
        except OSError as exc:
            raise LogSourceUnavailableError(
                f"Cannot read Magento {kind} log: {path}",
                context={"error": str(exc)},
            ) from exc

    async def _process_line(self, kind: MagentoLogKind, raw: str) -> None:
        if not raw:
            return

        import time

        is_failure, reason = self._classify(kind, raw)
        event = MagentoLogEvent(kind=kind, raw=raw, is_failure=is_failure, failure_reason=reason)

        async with self._lock:
            self._recent.append(event)
            self._recent = self._recent[-40:]

            if not is_failure:
                return

            now = time.monotonic()
            self._failure_times.append(now)
            self._failure_times = [
                t for t in self._failure_times if now - t <= self._window_seconds
            ]

            if len(self._failure_times) >= self._threshold_count:
                if now - self._last_fired_at < self._cooldown_seconds:
                    return
                await self._fire_anomaly(reason, len(self._failure_times))
                self._last_fired_at = now
                self._failure_times = []

    def _classify(self, kind: MagentoLogKind, raw: str) -> tuple[bool, str]:
        if kind == "access":
            match = self._ACCESS_RE.search(raw)
            if not match:
                return False, ""
            status = int(match.group("status"))
            if status >= 500:
                return True, f"HTTP {status} server errors"
            if status in {400, 404, 409, 429}:
                return True, f"HTTP {status} client/application errors"
            return False, ""

        match = self._MAGENTO_LEVEL_RE.search(raw)
        if not match:
            return False, ""
        level = match.group("level").upper()
        if level in {"ERROR", "CRITICAL", "ALERT", "EMERGENCY"}:
            return True, f"Magento {level} log entries"
        if kind == "system" and level == "WARNING":
            return True, "Magento WARNING system entries"
        return False, ""

    async def _fire_anomaly(self, reason: str, count: int) -> None:
        snippet = self._build_snippet()
        logger.warning(
            "magento_correlated_watcher.anomaly",
            reason=reason,
            count=count,
        )
        await self._bus.publish(
            LogAnomalyDetectedEvent(
                source=LogSource.MAGENTO.value,
                pattern=f"Magento correlated log failures: {reason}",
                occurrences=count,
                service="magento",
                log_snippet=snippet,
            )
        )

    def _build_snippet(self) -> str:
        lines = ["Magento correlated log anomaly evidence:"]
        for kind in ("exception", "system", "access"):
            matching = [e for e in self._recent if e.kind == kind]
            if not matching:
                continue
            lines.append(f"\n[{kind}.log]")
            for event in matching[-6:]:
                marker = "FAIL" if event.is_failure else "OK"
                lines.append(f"{marker}: {event.raw}")
        return "\n".join(lines)[-2000:]


class MultiSourceWatcher:
    """
    Composite watcher — manages multiple LogWatcher instances.
    Starts them concurrently and handles graceful shutdown.
    """

    def __init__(self, watchers: list[LogWatcher]) -> None:
        self._watchers = watchers
        self._tasks: list[asyncio.Task] = []

    async def start_all(self) -> None:
        self._tasks = [
            asyncio.create_task(w.start(), name=f"watcher-{self._watcher_name(w)}")
            for w in self._watchers
        ]
        logger.info("multi_watcher.started", count=len(self._watchers))

    async def stop_all(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("multi_watcher.stopped")

    @staticmethod
    def _watcher_name(watcher: object) -> str:
        source = getattr(watcher, "_source", None)
        if source is not None:
            return str(getattr(source, "value", source))
        return watcher.__class__.__name__.lower()
