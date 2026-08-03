"""
api/main.py
-----------
FastAPI application factory.

Pattern: Application Factory — create_app() builds the app,
allowing different configurations for test / production.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import AsyncIterator
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.v1.routers import dashboard, incidents, ops_mvp, rag
from core.config.settings import get_settings
from core.exceptions import BaseFrameworkError
from core.logging import configure_logging, get_logger
from models import HealthResponseSchema

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown lifecycle."""
    settings = get_settings()
    configure_logging(
        log_level=settings.log_level,
        json_logs=settings.is_production,
    )

    # Build FAISS index on startup
    try:
        from rag.indexer import FAISSIndexer  # noqa: PLC0415
        indexer = FAISSIndexer(settings)
        indexer.load_or_build()
        logger.info("app.startup.index_ready")
    except Exception as exc:
        logger.warning("app.startup.index_skipped", error=str(exc))

    # Start log watchers
    try:
        from log_monitors.watchers import (  # noqa: PLC0415
            LogWatcher,
            MagentoCorrelatedLogWatcher,
            MultiSourceWatcher,
        )
        from models import LogSource  # noqa: PLC0415
        from orchestration import OrchestratorBuilder  # noqa: PLC0415
        from core.events import LogAnomalyDetectedEvent, get_event_bus  # noqa: PLC0415
        from services.incident_store import IncidentStore  # noqa: PLC0415

        # Wire log anomaly → orchestrator
        orch = OrchestratorBuilder().with_settings(settings).build()
        incident_store = IncidentStore(settings)

        async def on_log_anomaly(event: LogAnomalyDetectedEvent) -> None:
            from models import AlertPayloadSchema  # noqa: PLC0415
            from services.observability import get_observability  # noqa: PLC0415
            incident_id = f"INC-{uuid4().hex[:8].upper()}"
            metrics = {
                "error_rate": min(1.0, event.occurrences / max(1, settings.magento_failure_threshold_count)),
            }
            trigger = {
                "event": asdict(event),
                "source": "log_anomaly_handler",
            }
            get_observability().record_anomaly(
                source=event.source,
                pattern=event.pattern,
                occurrences=event.occurrences,
                service=event.service,
                log_snippet=event.log_snippet,
            )
            payload = AlertPayloadSchema(
                incident_id=incident_id,
                service=event.service,
                alert_type="LogAnomaly",
                logs_snippet=event.log_snippet,
                log_source=event.source,
                metrics=metrics,
            )
            try:
                await incident_store.create_detected_incident(
                    incident_id=incident_id,
                    service=event.service,
                    alert_type="LogAnomaly",
                    log_source=event.source,
                    logs_snippet=event.log_snippet,
                    metrics=metrics,
                    trigger=trigger,
                )
                result = await orch.run(payload)
                await incident_store.save_pipeline_result(result, trigger=trigger)
            except Exception as exc:
                logger.error("log_anomaly_handler.error", error=str(exc))

        get_event_bus().subscribe(LogAnomalyDetectedEvent, on_log_anomaly)

        # Each path comes directly from settings — no glob mangling.
        # Users set exact file paths in .env for POC (e.g. PYTHON_LOG_PATH=../myapp/logs/app.log)
        watcher_list = []
        magento_paths = [
            settings.magento_exception_log_path,
            settings.magento_system_log_path,
            settings.magento_access_log_path,
        ]
        if all(path and path != "disabled" for path in magento_paths):
            watcher_list.append(
                MagentoCorrelatedLogWatcher(
                    exception_log_path=settings.magento_exception_log_path,
                    system_log_path=settings.magento_system_log_path,
                    access_log_path=settings.magento_access_log_path,
                    threshold_count=settings.magento_failure_threshold_count,
                    window_seconds=settings.magento_failure_window_seconds,
                    cooldown_seconds=settings.magento_incident_cooldown_seconds,
                    poll_interval_sec=settings.log_poll_interval_sec,
                )
            )
        else:
            logger.info("magento_correlated_watcher.skipped")

        for source, path in [
            (LogSource.AEM,     settings.aem_log_path),
            (LogSource.JAVA,    settings.java_log_path),
            (LogSource.PYTHON,  settings.python_log_path),
        ]:
            if path and path != "disabled":
                watcher_list.append(LogWatcher(source, path, poll_interval_sec=settings.log_poll_interval_sec))
            else:
                logger.info("log_watcher.skipped", source=source.value)

        watchers = MultiSourceWatcher(watcher_list)
        await watchers.start_all()
        app.state.watchers = watchers
        logger.info("app.startup.watchers_started")
    except Exception as exc:
        logger.warning("app.startup.watchers_skipped", error=str(exc))

    logger.info("app.startup.complete", mode=settings.app_mode.value)
    yield

    # Shutdown
    if hasattr(app.state, "watchers"):
        await app.state.watchers.stop_all()
    logger.info("app.shutdown.complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Agentic Support Framework",
        description=(
            "Production-grade agentic monitoring, RCA, and automated remediation. "
            "Supports Magento, AEM, Java, and Python log sources."
        ),
        version="1.0.0",
        openapi_url=f"{settings.api_v1_prefix}/openapi.json",
        docs_url=f"{settings.api_v1_prefix}/docs",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler — never leak internal details to clients
    @app.exception_handler(BaseFrameworkError)
    async def framework_error_handler(
        request: Request, exc: BaseFrameworkError
    ) -> JSONResponse:
        logger.error("unhandled_framework_error", path=request.url.path, error=exc.message)
        return JSONResponse(
            status_code=500,
            content={"detail": exc.message, "type": exc.__class__.__name__},
        )

    # Include routers
    app.include_router(incidents.router, prefix=settings.api_v1_prefix)
    app.include_router(rag.router, prefix=settings.api_v1_prefix)
    app.include_router(dashboard.router, prefix=settings.api_v1_prefix)
    app.include_router(ops_mvp.router)

    @app.get(f"{settings.api_v1_prefix}/health", response_model=HealthResponseSchema, tags=["system"])
    async def health() -> HealthResponseSchema:
        from services.llm import LLMFactory  # noqa: PLC0415
        llm = LLMFactory.create(settings)
        llm_health = await llm.health_check()
        return HealthResponseSchema(
            status="ok",
            environment=settings.environment.value,
            llm_provider=settings.llm_provider.value,
            llm_status=llm_health.get("status", "unknown"),
            vector_store=settings.vector_store.value,
            log_sources=["magento", "aem", "java", "python"],
        )

    return app


app = create_app()
