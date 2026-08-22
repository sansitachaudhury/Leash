"""
The heart of Leash: given a proposed action + session context, produce a
risk score and a verdict (allow / review / block), with an explanation.

    risk_score = w1*semantic_drift + w2*anomaly_score + w3*sensitivity_score

blended rather than max()'d, so a single moderately-off signal doesn't block
outright, but multiple weak signals stacking up will — mirroring how a real
"drift toward a sensitive action" pattern looks over several steps too.
"""
from __future__ import annotations
from typing import Any

from backend.config import (
    BLOCK_THRESHOLD, REVIEW_THRESHOLD,
    WEIGHT_SEMANTIC_DRIFT, WEIGHT_ANOMALY, WEIGHT_SENSITIVITY,
    TOOL_SENSITIVITY, DEFAULT_TOOL_SENSITIVITY,
)
from backend.models.schemas import ScoreResult, Verdict
from backend.security.feature_extractor import SessionState, extract_features, feature_vector
from backend.security.semantic_drift import get_scorer as get_semantic_scorer
from backend.security.anomaly_model import get_model
from backend.security.explainer import explain, explanation_summary


def score_action(
    task: str,
    tool_name: str,
    arguments: dict[str, Any],
    step_index: int,
    session: SessionState,
) -> ScoreResult:
    # 1. Semantic drift: does this action still relate to the stated task?
    similarity, drift_score = get_semantic_scorer().score(task, tool_name, arguments)

    # 2. Behavioral anomaly: does this look like an outlier vs. normal sessions?
    features = extract_features(tool_name, arguments, step_index, session)
    model = get_model()
    anomaly_score = model.score(feature_vector(features)) if model.is_ready() else 0.0

    # 3. Static sensitivity of the action itself.
    sensitivity_score = float(TOOL_SENSITIVITY.get(tool_name, DEFAULT_TOOL_SENSITIVITY))

    risk_score = (
        WEIGHT_SEMANTIC_DRIFT * drift_score
        + WEIGHT_ANOMALY * anomaly_score
        + WEIGHT_SENSITIVITY * sensitivity_score
    )
    risk_score = max(0.0, min(100.0, risk_score))

    if risk_score >= BLOCK_THRESHOLD:
        verdict = Verdict.BLOCK
    elif risk_score >= REVIEW_THRESHOLD:
        verdict = Verdict.REVIEW
    else:
        verdict = Verdict.ALLOW

    contributions = explain(features, model)

    # Record this call in session history AFTER feature extraction (features
    # should reflect state *before* this call, e.g. "is this a new tool").
    session.record(tool_name)

    return ScoreResult(
        semantic_similarity=similarity,
        semantic_drift_score=drift_score,
        anomaly_score=anomaly_score,
        sensitivity_score=sensitivity_score,
        risk_score=risk_score,
        verdict=verdict,
        top_contributions=contributions[:5],
        raw_features=features,
    )


def build_explanation(result: ScoreResult) -> str:
    return explanation_summary(result.top_contributions, result.verdict.value)
