"""
Semantic risk scoring for agent actions.
Uses sentence embeddings to detect goal drift and combines with tool sensitivity
for a composite risk score with explainability breakdown.
"""
import json
from collections import OrderedDict
import numpy as np
from sentence_transformers import SentenceTransformer
import config
from log import get_logger

log = get_logger("core.risk")

# Bounded LRU cache to prevent memory leaks
_MAX_CACHE = 2048


class _EmbeddingCache:
    """Bounded LRU cache for sentence embeddings."""

    def __init__(self, max_size: int = _MAX_CACHE):
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._max_size = max_size

    def get(self, text: str) -> np.ndarray | None:
        if text in self._cache:
            self._cache.move_to_end(text)
            return self._cache[text]
        return None

    def put(self, text: str, embedding: np.ndarray):
        if text in self._cache:
            self._cache.move_to_end(text)
        else:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)  # evict oldest
            self._cache[text] = embedding

    def __len__(self):
        return len(self._cache)


_cache = _EmbeddingCache()
_model = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        log.info("Loading sentence-transformers model (all-MiniLM-L6-v2)...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        log.info("Model loaded")
    return _model


def embed(text: str) -> np.ndarray:
    """Embed text with bounded LRU caching."""
    cached = _cache.get(text)
    if cached is not None:
        return cached
    model = _get_model()
    vec = model.encode(text, normalize_embeddings=True)
    _cache.put(text, vec)
    return vec


def semantic_drift(task_embedding: np.ndarray, action_desc: str) -> float:
    """Compute semantic distance between the task and an action. 0 = on-task, 1 = unrelated."""
    action_emb = embed(action_desc)
    cos = float(np.dot(task_embedding, action_emb))
    return (1 - cos) / 2


def step_risk(task_embedding, tool_name: str, tool_args: dict, history: list) -> dict:
    """
    Compute composite risk score for a single agent step.

    Combines:
      - Tool sensitivity (predefined risk weight per tool)
      - Semantic drift (how far the action is from the task)
      - Repetition (tool called repeatedly)

    Returns dict with risk_score [0..1] and explainability breakdown.
    """
    action_desc = f"{tool_name} {json.dumps(tool_args)}"
    drift = semantic_drift(task_embedding, action_desc)
    sensitivity = config.TOOL_SENSITIVITY.get(tool_name, 0.5)
    repeats = sum(1 for h in history[-4:] if h == tool_name)

    # Weighted composite risk
    risk = min(0.5 * sensitivity + 0.35 * drift + 0.15 * min(repeats / 3, 1.0), 1.0)

    # SHAP-style feature contributions for explainability
    sensitivity_impact = round(0.5 * sensitivity, 3)
    drift_impact = round(0.35 * drift, 3)
    repetition_impact = round(0.15 * min(repeats / 3, 1.0), 3)

    return {
        "tool_sensitivity": round(sensitivity, 3),
        "semantic_drift": round(drift, 3),
        "repetition_count": repeats,
        "risk_score": round(risk, 3),
        "explainability": {
            "sensitivity_impact": sensitivity_impact,
            "drift_impact": drift_impact,
            "repetition_impact": repetition_impact,
            "total": round(risk, 3),
        },
    }
