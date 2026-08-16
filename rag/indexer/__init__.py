"""
rag/indexer/__init__.py
-----------------------
FAISS vector index builder.
Uses services/embedding — auto-selects SentenceTransformer or offline TF-IDF.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np

from core.exceptions import VectorStoreError, VectorStoreNotInitialisedError
from core.logging import get_logger
from services.model_egress import sanitize_for_embedding

logger = get_logger(__name__)


class FAISSIndexer:
    """Builds and persists a FAISS flat-L2 index from knowledge base documents."""

    def __init__(self, settings: object) -> None:
        from core.config.settings import Settings
        self._settings: Settings = settings  # type: ignore[assignment]
        self._embedder = None
        self._index = None
        self._chunks: list[dict] = []

    @property
    def _index_bin(self) -> Path:
        return Path(str(self._settings.faiss_index_path) + ".index")

    @property
    def _index_meta(self) -> Path:
        return Path(str(self._settings.faiss_index_path) + "_meta.pkl")

    @property
    def _embedder_path(self) -> Path:
        return Path(str(self._settings.faiss_index_path) + "_embedder.pkl")

    def load_or_build(self) -> None:
        if self._index_bin.exists() and self._index_meta.exists():
            self._load()
        else:
            self.build(force=True)

    def build(self, force: bool = False) -> None:
        try:
            import faiss  # noqa: PLC0415
        except ImportError as exc:
            raise VectorStoreError("faiss-cpu not installed") from exc

        if not force and self._index_bin.exists():
            return

        chunks = self._collect_chunks()
        if not chunks:
            logger.warning("rag.indexer.empty_kb")
            self._chunks = []
            return

        embedder = self._get_embedder(chunks)
        chunks = [self._sanitize_chunk_for_embedding(chunk) for chunk in chunks]
        texts = [c["text"] for c in chunks]
        logger.info("rag.indexer.encoding", count=len(texts),
                    embedder=embedder.__class__.__name__)

        embeddings = embedder.encode(texts)
        embeddings = np.array(embeddings, dtype="float32")

        dim = embeddings.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(embeddings)

        self._index_bin.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(self._index_bin))
        self._index_meta.write_bytes(pickle.dumps(chunks))
        # Save embedder if it's a fitted TF-IDF so we can reuse it at query time
        from services.embedding import TFIDFEmbedder  # noqa: PLC0415
        if isinstance(embedder, TFIDFEmbedder):
            embedder.save(self._embedder_path)

        self._index = index
        self._chunks = chunks
        self._embedder = embedder
        logger.info("rag.indexer.built", chunks=len(chunks), dim=dim)

    def _load(self) -> None:
        try:
            import faiss  # noqa: PLC0415
            self._index = faiss.read_index(str(self._index_bin))
            self._chunks = pickle.loads(self._index_meta.read_bytes())  # noqa: S301
            # Re-load embedder
            self._embedder = self._restore_embedder()
            logger.info("rag.indexer.loaded", chunks=len(self._chunks))
        except Exception as exc:
            raise VectorStoreError(f"Failed to load FAISS index: {exc}") from exc

    def _restore_embedder(self):
        from services.embedding import TFIDFEmbedder, get_embedder  # noqa: PLC0415
        if self._embedder_path.exists():
            logger.info("rag.indexer.loading_tfidf_embedder")
            return TFIDFEmbedder.load(self._embedder_path)
        return get_embedder(self._settings.embed_model, self._settings.embed_device)

    def _get_embedder(self, corpus_chunks: list[dict]):
        from services.embedding import TFIDFEmbedder, get_embedder  # noqa: PLC0415
        embedder = get_embedder(self._settings.embed_model, self._settings.embed_device)
        if isinstance(embedder, TFIDFEmbedder):
            logger.info("rag.indexer.fitting_tfidf", corpus_size=len(corpus_chunks))
            embedder.fit([c["text"] for c in corpus_chunks])
        return embedder

    def search(self, query_embedding: np.ndarray, top_k: int) -> list[dict]:
        if self._index is None or not self._chunks:
            raise VectorStoreNotInitialisedError("Index not loaded. Call load_or_build() first.")
        distances, indices = self._index.search(query_embedding, top_k)
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if 0 <= idx < len(self._chunks):
                chunk = self._chunks[idx].copy()
                chunk["score"] = float(dist)
                results.append(chunk)
        return results

    def get_embedder(self):
        return self._embedder

    def _collect_chunks(self) -> list[dict]:
        all_chunks: list[dict] = []
        kb_path = Path(self._settings.knowledge_base_path)
        if kb_path.exists():
            for fpath in kb_path.rglob("*"):
                if fpath.suffix in {".md", ".txt", ".psv"}:
                    try:
                        text = fpath.read_text(encoding="utf-8")
                        all_chunks.extend(self._chunk_text(text, fpath.name))
                    except OSError as exc:
                        logger.warning("rag.indexer.read_error",
                                       file=str(fpath), error=str(exc))

        incident_file = Path("./data/sample_incidents/incidents.json")
        if incident_file.exists():
            incidents = json.loads(incident_file.read_text())
            for inc in incidents:
                if inc.get("resolved"):
                    text = (
                        f"Incident {inc['incident_id']} service={inc['service']} "
                        f"type={inc['alert_type']}. Symptoms: {inc.get('logs_snippet','')}. "
                        f"Resolution: {inc.get('resolution','')}. "
                        f"MTTR: {inc.get('mttr_minutes',0)} minutes."
                    )
                    all_chunks.append({
                        "text": text,
                        "source": "incident_history",
                        "chunk_id": inc["incident_id"],
                    })
        return all_chunks

    def _sanitize_chunk_for_embedding(self, chunk: dict) -> dict:
        sanitized = sanitize_for_embedding(str(chunk.get("text", "")), self._settings)
        safe_chunk = chunk.copy()
        safe_chunk["text"] = sanitized.text
        if sanitized.was_modified:
            safe_chunk["model_egress_redactions"] = {
                item.category: item.count for item in sanitized.redactions
            }
        return safe_chunk

    @staticmethod
    def _chunk_text(text: str, source: str,
                    chunk_size: int = 400, overlap: int = 80) -> list[dict]:
        words = text.split()
        if not words:
            return []
        chunks = []
        step = max(1, chunk_size - overlap)
        for i in range(0, len(words), step):
            chunk = " ".join(words[i: i + chunk_size])
            if chunk.strip():
                chunks.append({
                    "text": chunk,
                    "source": source,
                    "chunk_id": f"{source}-{len(chunks)}",
                })
        return chunks
