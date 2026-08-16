"""
rag/retriever/__init__.py
--------------------------
RAG retriever — encodes a query and returns ranked context chunks.
Uses the same embedder that was used to build the index.
"""
from __future__ import annotations

import numpy as np

from core.logging import get_logger
from models import ContextChunk
from rag.indexer import FAISSIndexer
from services.model_egress import sanitize_for_embedding

logger = get_logger(__name__)


class RAGRetriever:
    """Retrieves semantically relevant context chunks for a query string."""

    def __init__(self, indexer: FAISSIndexer, settings: object) -> None:
        self._indexer = indexer
        self._settings = settings

    async def retrieve(self, query: str, top_k: int | None = None) -> list[ContextChunk]:
        k = top_k or self._settings.rag_top_k
        embedder = self._indexer.get_embedder()
        if embedder is None:
            logger.warning("rag.retrieve.no_embedder")
            return []

        safe_query = sanitize_for_embedding(query, self._settings).text
        q_vec = embedder.encode([safe_query])
        raw = self._indexer.search(q_vec, top_k=k)

        chunks = [
            ContextChunk(
                text=r["text"],
                source=r["source"],
                chunk_id=str(r["chunk_id"]),
                score=r["score"],
            )
            for r in raw
        ]
        logger.debug("rag.retrieve", query_len=len(safe_query), returned=len(chunks))
        return chunks
