"""
services/embedding/__init__.py
-------------------------------
Embedding service with two backends:
  - SentenceTransformerEmbedder  (needs HuggingFace download)
  - TFIDFEmbedder                (pure scikit-learn, fully offline)

The factory auto-selects TFIDFEmbedder when SentenceTransformers
cannot reach HuggingFace (CI, air-gapped, or network-restricted envs).
"""
from __future__ import annotations

import abc
import pickle
from pathlib import Path

import numpy as np


class BaseEmbedder(abc.ABC):
    @abc.abstractmethod
    def fit(self, texts: list[str]) -> None: ...

    @abc.abstractmethod
    def encode(self, texts: list[str]) -> np.ndarray: ...

    @property
    @abc.abstractmethod
    def dim(self) -> int: ...


class TFIDFEmbedder(BaseEmbedder):
    """
    Offline TF-IDF + SVD + L2-normalise pipeline.
    No network calls, no model files, deterministic.
    """

    def __init__(self, n_components: int = 8) -> None:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import Normalizer

        self._pipe = make_pipeline(
            TfidfVectorizer(
                sublinear_tf=True,
                max_features=8000,
                ngram_range=(1, 2),
                min_df=1,
                strip_accents="unicode",
            ),
            TruncatedSVD(n_components=n_components, random_state=42),
            Normalizer(copy=False),
        )
        self._n_components = n_components
        self._fitted = False

    def fit(self, texts: list[str]) -> None:
        self._pipe.fit(texts)
        self._fitted = True

    def encode(self, texts: list[str]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("Call fit() before encode()")
        return np.array(self._pipe.transform(texts), dtype="float32")

    @property
    def dim(self) -> int:
        return self._n_components

    def save(self, path: Path) -> None:
        path.write_bytes(pickle.dumps(self._pipe))

    @classmethod
    def load(cls, path: Path, n_components: int = 8) -> "TFIDFEmbedder":
        obj = cls(n_components=n_components)
        obj._pipe = pickle.loads(path.read_bytes())  # noqa: S301
        obj._fitted = True
        return obj


def get_embedder(model_name: str = "all-MiniLM-L6-v2", device: str = "cpu") -> BaseEmbedder:
    """Return SentenceTransformer if available; otherwise TFIDFEmbedder."""
    if model_name.lower() in {"tfidf", "offline", "local"}:
        return TFIDFEmbedder()

    try:
        from sentence_transformers import SentenceTransformer as ST  # noqa: PLC0415

        class _STWrapper(BaseEmbedder):
            def __init__(self) -> None:
                self._m = ST(model_name, device=device)

            def fit(self, texts: list[str]) -> None:
                pass  # pre-trained, no fitting needed

            def encode(self, texts: list[str]) -> np.ndarray:
                return self._m.encode(texts, convert_to_numpy=True,
                                      show_progress_bar=False).astype("float32")

            @property
            def dim(self) -> int:
                return self._m.get_sentence_embedding_dimension()

        wrapper = _STWrapper()
        wrapper.encode(["warmup"])   # raises if model can't be downloaded
        return wrapper
    except Exception:
        return TFIDFEmbedder()
