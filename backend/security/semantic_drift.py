"""
Measures how semantically related a proposed action is to the task the agent
was actually given. This is what catches "the task was 'summarize invoices'
but the agent is now calling transfer_funds" even when the behavioral stats
alone look unremarkable.

Primary path: sentence-transformers local embeddings (per the tech stack).
Fallback path: TF-IDF + cosine similarity (scikit-learn), used automatically
if the transformer model can't be loaded (e.g. no network access to download
weights). This keeps the demo alive offline, in the spirit of the deck's
"Resilience: demo-safe if the live API drops" line.
"""
from __future__ import annotations
import logging
from typing import Any

import numpy as np

from backend.config import SENTENCE_MODEL_NAME

logger = logging.getLogger("leash.semantic_drift")


def _describe_action(tool_name: str, arguments: dict[str, Any]) -> str:
    """Turn a tool call into a short natural-language description for embedding."""
    arg_str = ", ".join(f"{k}={v}" for k, v in arguments.items())
    return f"{tool_name.replace('_', ' ')}: {arg_str}"


class _SentenceTransformerBackend:
    def __init__(self, model_name: str = SENTENCE_MODEL_NAME):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)

    def similarity(self, task: str, action_text: str) -> float:
        from sentence_transformers.util import cos_sim
        emb = self.model.encode([task, action_text], normalize_embeddings=True)
        sim = float(cos_sim(emb[0], emb[1])[0][0])
        return max(0.0, min(1.0, (sim + 1) / 2))  # map [-1,1] -> [0,1]


class _TfidfBackend:
    """Lightweight fallback: no download required, ships with scikit-learn."""
    def similarity(self, task: str, action_text: str) -> float:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        vec = TfidfVectorizer().fit([task, action_text])
        matrix = vec.transform([task, action_text])
        sim = cosine_similarity(matrix[0], matrix[1])[0][0]
        return float(max(0.0, min(1.0, sim)))


class SemanticDriftScorer:
    """
    Lazily loads the best available backend once, then reuses it. Exposed as a
    module-level singleton (`get_scorer()`) so the embedding model is loaded
    once per process, not once per request.
    """
    def __init__(self):
        self._backend = None
        self._backend_name = "uninitialized"

    def _ensure_backend(self):
        if self._backend is not None:
            return
        try:
            self._backend = _SentenceTransformerBackend()
            self._backend_name = f"sentence-transformers ({SENTENCE_MODEL_NAME})"
            logger.info("Semantic drift backend: %s", self._backend_name)
        except Exception as e:  # noqa: BLE001 - broad on purpose, this is a fallback path
            logger.warning(
                "Could not load sentence-transformers (%s). Falling back to TF-IDF. "
                "This is expected in offline/no-network environments.", e
            )
            self._backend = _TfidfBackend()
            self._backend_name = "tfidf-fallback"

    @property
    def backend_name(self) -> str:
        self._ensure_backend()
        return self._backend_name

    def score(self, task: str, tool_name: str, arguments: dict[str, Any]) -> tuple[float, float]:
        """Returns (similarity 0-1, drift_score 0-100)."""
        self._ensure_backend()
        action_text = _describe_action(tool_name, arguments)
        similarity = self._backend.similarity(task, action_text)
        drift_score = float(np.clip((1.0 - similarity) * 100, 0, 100))
        return similarity, drift_score


_singleton: SemanticDriftScorer | None = None


def get_scorer() -> SemanticDriftScorer:
    global _singleton
    if _singleton is None:
        _singleton = SemanticDriftScorer()
    return _singleton
