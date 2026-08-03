"""
api/v1/routers/rag.py
---------------------
RAG validation and index management endpoints.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from core.config.settings import Settings, get_settings
from core.exceptions import BaseFrameworkError
from core.logging import get_logger
from models import (
    RAGHealthResponseSchema,
    RAGRebuildResponseSchema,
    RAGSearchRequestSchema,
    RAGSearchResponseSchema,
    RAGSearchResultSchema,
)
from rag.indexer import FAISSIndexer
from rag.retriever import RAGRetriever

logger = get_logger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])

_indexer: FAISSIndexer | None = None


def _index_paths(settings: Settings) -> tuple[Path, Path, Path]:
    base = Path(str(settings.faiss_index_path))
    return (
        Path(str(base) + ".index"),
        Path(str(base) + "_meta.pkl"),
        Path(str(base) + "_embedder.pkl"),
    )


def _get_indexer(settings: Settings = Depends(get_settings)) -> FAISSIndexer:
    global _indexer
    if _indexer is None:
        indexer = FAISSIndexer(settings)
        indexer.load_or_build()
        _indexer = indexer
    return _indexer


def _embedder_info(indexer: FAISSIndexer) -> tuple[str | None, int | None]:
    embedder = indexer.get_embedder()
    if embedder is None:
        return None, None
    dim = getattr(embedder, "dim", None)
    return embedder.__class__.__name__, int(dim) if dim is not None else None


def _source_counts(indexer: FAISSIndexer) -> dict[str, int]:
    chunks: list[dict[str, Any]] = getattr(indexer, "_chunks", [])
    return dict(Counter(str(chunk.get("source", "unknown")) for chunk in chunks))


@router.get(
    "/health",
    response_model=RAGHealthResponseSchema,
    summary="Return RAG index health and metadata",
)
async def rag_health(
    settings: Settings = Depends(get_settings),
    indexer: FAISSIndexer = Depends(_get_indexer),
) -> RAGHealthResponseSchema:
    index_path, meta_path, embedder_path = _index_paths(settings)
    embedder_type, embedder_dim = _embedder_info(indexer)
    chunk_count = len(getattr(indexer, "_chunks", []))

    return RAGHealthResponseSchema(
        status="ok" if index_path.exists() and meta_path.exists() and chunk_count else "not_ready",
        vector_store=settings.vector_store.value,
        knowledge_base_path=str(settings.knowledge_base_path),
        index_path=str(index_path),
        index_exists=index_path.exists(),
        metadata_exists=meta_path.exists(),
        embedder_exists=embedder_path.exists(),
        loaded=chunk_count > 0 and indexer.get_embedder() is not None,
        chunk_count=chunk_count,
        embedder_type=embedder_type,
        embedder_dim=embedder_dim,
        sources=_source_counts(indexer),
    )


@router.post(
    "/search",
    response_model=RAGSearchResponseSchema,
    summary="Search the RAG knowledge base",
)
async def rag_search(
    payload: RAGSearchRequestSchema,
    settings: Settings = Depends(get_settings),
    indexer: FAISSIndexer = Depends(_get_indexer),
) -> RAGSearchResponseSchema:
    try:
        retriever = RAGRetriever(indexer=indexer, settings=settings)
        chunks = await retriever.retrieve(payload.query, top_k=payload.top_k)
        return RAGSearchResponseSchema(
            query=payload.query,
            top_k=payload.top_k,
            results=[
                RAGSearchResultSchema(
                    source=chunk.source,
                    chunk_id=chunk.chunk_id,
                    score=chunk.score,
                    text=chunk.text,
                )
                for chunk in chunks
            ],
        )
    except BaseFrameworkError as exc:
        logger.error("api.rag.search.error", error=exc.message, context=exc.context)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": exc.message, "context": exc.context},
        ) from exc


@router.post(
    "/rebuild",
    response_model=RAGRebuildResponseSchema,
    summary="Rebuild the RAG vector index from the knowledge base",
)
async def rag_rebuild(
    settings: Settings = Depends(get_settings),
) -> RAGRebuildResponseSchema:
    global _indexer
    try:
        indexer = FAISSIndexer(settings)
        indexer.build(force=True)
        _indexer = indexer

        index_path, meta_path, embedder_path = _index_paths(settings)
        embedder_type, embedder_dim = _embedder_info(indexer)
        chunk_count = len(getattr(indexer, "_chunks", []))

        return RAGRebuildResponseSchema(
            status="rebuilt",
            chunk_count=chunk_count,
            embedder_type=embedder_type,
            embedder_dim=embedder_dim,
            index_path=str(index_path),
            metadata_path=str(meta_path),
            embedder_path=str(embedder_path),
        )
    except BaseFrameworkError as exc:
        logger.error("api.rag.rebuild.error", error=exc.message, context=exc.context)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": exc.message, "context": exc.context},
        ) from exc
