"""
Explains a risk decision at the feature level using SHAP, so every block
comes with "why" rather than a bare score. Falls back to a simple sensitivity
analysis (perturb-one-feature-at-a-time) if SHAP isn't available/installed,
so the pipeline never hard-fails on missing XAI tooling during a demo.
"""
from __future__ import annotations
import logging
from typing import Any

import numpy as np

from backend.security.feature_extractor import FEATURE_NAMES
from backend.models.schemas import FeatureContribution

logger = logging.getLogger("leash.explainer")
logging.getLogger("shap").setLevel(logging.WARNING)  # shap's own logger is very chatty at INFO

_explainer_cache = {}  # keyed by id(anomaly_model) so we build the KernelExplainer once

FEATURE_DESCRIPTIONS = {
    "tool_sensitivity": "How damaging this tool is if misused",
    "step_index_norm": "How far into the session this call happens",
    "seconds_since_start": "Elapsed time since the task began",
    "call_rate": "Tool calls per second (burstiness)",
    "is_new_tool_for_session": "Tool not previously used in this session",
    "arg_length": "Size of the arguments payload",
    "out_of_scope_keyword_hits": "Suspicious keywords in the arguments",
    "repeat_tool_streak": "Consecutive identical-tool calls just before this one",
}

_background_cache: np.ndarray | None = None


def _get_background(anomaly_model) -> np.ndarray:
    """A small synthetic background set around 'typical' scaled feature values,
    used as the SHAP baseline. Zeros in *scaled* space = the training mean."""
    global _background_cache
    if _background_cache is None:
        _background_cache = np.zeros((8, len(FEATURE_NAMES)))
    return _background_cache


def explain(
    features: dict[str, float],
    anomaly_model,
) -> list[FeatureContribution]:
    """
    Returns feature contributions sorted by |impact| descending, using SHAP's
    KernelExplainer over the anomaly model's scoring function when available.
    """
    fvec = np.array([features[name] for name in FEATURE_NAMES])

    if not anomaly_model.is_ready():
        # No trained model yet: fall back to raw-value ranking only.
        return _fallback_ranking(features)

    def predict_fn(X: np.ndarray) -> np.ndarray:
        return anomaly_model.score_batch(X)

    try:
        import shap

        cache_key = id(anomaly_model)
        explainer = _explainer_cache.get(cache_key)
        if explainer is None:
            background = _get_background(anomaly_model)
            explainer = shap.KernelExplainer(predict_fn, background, silent=True)
            _explainer_cache[cache_key] = explainer

        # nsamples kept small: 8 features, this is a real-time interception path,
        # not an offline analysis job. Good enough for a directionally-correct
        # top-3 explanation, which is all the UI surfaces anyway.
        shap_values = explainer.shap_values(fvec.reshape(1, -1), nsamples=24, silent=True)
        shap_values = np.array(shap_values).flatten()

        contributions = [
            FeatureContribution(
                feature=name,
                value=float(features[name]),
                contribution=float(shap_values[i]),
                description=FEATURE_DESCRIPTIONS.get(name, name),
            )
            for i, name in enumerate(FEATURE_NAMES)
        ]
        contributions.sort(key=lambda c: abs(c.contribution), reverse=True)
        return contributions
    except Exception as e:  # noqa: BLE001 - explanation must never crash scoring
        logger.warning("SHAP explanation failed (%s), using fallback ranking.", e)
        return _fallback_ranking(features)


def _fallback_ranking(features: dict[str, float]) -> list[FeatureContribution]:
    """Simple heuristic ranking: normalize each raw feature against a rough
    'typical' scale and rank by how far it deviates. Used if SHAP/model are
    unavailable, so the UI always has *something* to show."""
    typical = {
        "tool_sensitivity": 20, "step_index_norm": 0.3, "seconds_since_start": 5,
        "call_rate": 0.2, "is_new_tool_for_session": 0, "arg_length": 40,
        "out_of_scope_keyword_hits": 0, "repeat_tool_streak": 0,
    }
    contributions = []
    for name in FEATURE_NAMES:
        val = features[name]
        base = typical.get(name, 1) or 1
        deviation = (val - base) / (abs(base) + 1)
        contributions.append(FeatureContribution(
            feature=name, value=float(val), contribution=float(deviation),
            description=FEATURE_DESCRIPTIONS.get(name, name),
        ))
    contributions.sort(key=lambda c: abs(c.contribution), reverse=True)
    return contributions


def explanation_summary(contributions: list[FeatureContribution], verdict: str) -> str:
    top = contributions[:3]
    parts = [f"{c.description} ({c.value:.1f})" for c in top if c.contribution > 0] or \
            [f"{c.description} ({c.value:.1f})" for c in top]
    joined = "; ".join(parts)
    if verdict == "block":
        return f"Blocked primarily due to: {joined}."
    if verdict == "review":
        return f"Flagged for review due to: {joined}."
    return f"Allowed — no strong risk signal (top factors were minor: {joined})."
