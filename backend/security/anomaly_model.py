"""
scikit-learn IsolationForest wrapper. Trained on features extracted from
*normal* agent behavior only (unsupervised, the way IsolationForest is meant
to be used) so it learns what "typical" tool-call behavior looks like and
flags outliers at inference time.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from backend.config import ISOLATION_FOREST_PATH, SCALER_PATH, FEATURE_NAMES_PATH
from backend.security.feature_extractor import FEATURE_NAMES

logger = logging.getLogger("leash.anomaly_model")


class AnomalyModel:
    def __init__(self):
        self.model: IsolationForest | None = None
        self.scaler: StandardScaler | None = None

    # -- training --------------------------------------------------------
    def fit(self, X: np.ndarray, contamination: float = 0.08) -> None:
        """
        X: (n_samples, n_features) of NORMAL behavior. `contamination` is our
        prior on what fraction of training data might still be borderline/
        noisy, not the real-world attack rate.
        """
        self.scaler = StandardScaler().fit(X)
        X_scaled = self.scaler.transform(X)
        self.model = IsolationForest(
            n_estimators=200,
            contamination=contamination,
            random_state=42,
            max_samples="auto",
        )
        self.model.fit(X_scaled)
        logger.info("IsolationForest fit on %d samples, %d features", *X.shape)

    def save(self) -> None:
        assert self.model is not None and self.scaler is not None, "fit() before save()"
        joblib.dump(self.model, ISOLATION_FOREST_PATH)
        joblib.dump(self.scaler, SCALER_PATH)
        FEATURE_NAMES_PATH.write_text(json.dumps(FEATURE_NAMES, indent=2))
        logger.info("Saved model to %s", ISOLATION_FOREST_PATH)

    def load(self) -> bool:
        if not (Path(ISOLATION_FOREST_PATH).exists() and Path(SCALER_PATH).exists()):
            return False
        self.model = joblib.load(ISOLATION_FOREST_PATH)
        self.scaler = joblib.load(SCALER_PATH)
        return True

    # -- inference ---------------------------------------------------------
    def score(self, feature_vector: list[float]) -> float:
        """
        Returns an anomaly score in [0, 100], higher = more anomalous.
        IsolationForest's decision_function returns higher = more normal, so
        we invert and rescale via a squashing function calibrated around 0.
        """
        return float(self.score_batch(np.array([feature_vector]))[0])

    def score_batch(self, X: np.ndarray) -> np.ndarray:
        """Vectorized version of score() for many rows at once. Used by the
        SHAP explainer, which evaluates hundreds of perturbed feature rows per
        explanation — looping score() per row there was the #1 latency cost
        (each StandardScaler/IsolationForest call has fixed Python overhead,
        so batching is what makes explanations fast enough for a live demo)."""
        if self.model is None or self.scaler is None:
            raise RuntimeError("AnomalyModel not loaded/fit yet")
        X_scaled = self.scaler.transform(X)
        raw = self.model.decision_function(X_scaled)  # shape (n,)
        anomaly = 100.0 / (1.0 + np.exp(12 * (raw + 0.02)))
        return np.clip(anomaly, 0, 100)

    def is_ready(self) -> bool:
        return self.model is not None and self.scaler is not None


_singleton: AnomalyModel | None = None


def get_model() -> AnomalyModel:
    global _singleton
    if _singleton is None:
        _singleton = AnomalyModel()
        if not _singleton.load():
            logger.warning(
                "No trained IsolationForest found at %s — run `python scripts/train_model.py` "
                "first. Falling back to an untrained heuristic (0 anomaly score) until then.",
                ISOLATION_FOREST_PATH,
            )
    return _singleton
