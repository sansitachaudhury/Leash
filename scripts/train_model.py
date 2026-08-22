#!/usr/bin/env python3
"""
Generates synthetic normal-behavior training data, fits the IsolationForest,
and saves it + the feature scaler to backend/security/models/.

Run: python scripts/train_model.py
"""
import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import TRAINING_DATA_PATH
from backend.data.seed_data import generate_normal_sessions
from backend.security.anomaly_model import AnomalyModel
from backend.security.feature_extractor import FEATURE_NAMES, feature_vector

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("leash.train")


def main(n_sessions: int = 400):
    logger.info("Generating %d synthetic normal sessions...", n_sessions)
    rows = generate_normal_sessions(n_sessions)
    logger.info("Generated %d normal action rows.", len(rows))

    TRAINING_DATA_PATH.write_text(json.dumps(rows, indent=2))
    logger.info("Saved raw training data to %s", TRAINING_DATA_PATH)

    X = np.array([feature_vector(r) for r in rows])
    logger.info("Feature matrix shape: %s, features: %s", X.shape, FEATURE_NAMES)

    model = AnomalyModel()
    model.fit(X, contamination=0.08)
    model.save()

    # Quick sanity check: score a few normal + a couple of obviously-bad synthetic rows
    sample_normal = X[:5]
    for i, row in enumerate(sample_normal):
        logger.info("normal sample %d -> anomaly score %.1f", i, model.score(list(row)))

    bad_row = {
        "tool_sensitivity": 95, "step_index_norm": 0.9, "seconds_since_start": 0.5,
        "call_rate": 0.9, "is_new_tool_for_session": 1, "arg_length": 120,
        "out_of_scope_keyword_hits": 3, "repeat_tool_streak": 0,
    }
    logger.info("synthetic attack-like row -> anomaly score %.1f",
                model.score(feature_vector(bad_row)))

    logger.info("Done. Model artifacts saved under backend/security/models/")


if __name__ == "__main__":
    main()
