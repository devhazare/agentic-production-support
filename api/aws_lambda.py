from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from mangum import Mangum

from api.v1.routers import dashboard, incidents, ops_mvp
from core.config.settings import get_settings
from models import (
    IncidentEvent,
    RAGSearchRequestSchema,
    RAGSearchResponseSchema,
    RAGSearchResultSchema,
)
from services.aws_knowledge import KnowledgeService

app = FastAPI(title="AI Operational Intelligence MVP", version="0.1.0")
settings = get_settings()

app.include_router(incidents.router, prefix=settings.api_v1_prefix)
app.include_router(dashboard.router, prefix=settings.api_v1_prefix)
app.include_router(ops_mvp.router)


@app.post(f"{settings.api_v1_prefix}/rag/search", response_model=RAGSearchResponseSchema)
async def rag_search(payload: RAGSearchRequestSchema) -> RAGSearchResponseSchema:
    event = IncidentEvent(
        incident_id="rag-search-preview",
        service_name="knowledge-base",
        severity="Low",
        timestamp=datetime.now(timezone.utc).isoformat(),
        alert_type="ManualSearch",
        metric_name="query",
        metric_value=0,
        logs_summary=payload.query,
    )
    docs = KnowledgeService(settings).search(event, top_k=payload.top_k)
    return RAGSearchResponseSchema(
        query=payload.query,
        top_k=payload.top_k,
        results=[
            RAGSearchResultSchema(
                source=doc.source_uri,
                chunk_id=doc.document_id,
                score=doc.score,
                text=doc.text,
            )
            for doc in docs
        ],
    )


handler = Mangum(app)
