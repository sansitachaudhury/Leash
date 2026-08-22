"""
Converts a proposed action (+ its session context) into the fixed-length
numeric feature vector that both the IsolationForest and SHAP operate on.

Keeping this in one place means the trainer, the live scorer, and the
explainer all agree on what "feature 3" means.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any

from backend.config import OUT_OF_SCOPE_KEYWORDS, TOOL_SENSITIVITY, DEFAULT_TOOL_SENSITIVITY

FEATURE_NAMES = [
    "tool_sensitivity",       # static risk of this tool (0-100)
    "step_index_norm",        # how far into the session we are (0-1)
    "seconds_since_start",    # wall-clock time since task began
    "call_rate",              # tool calls per second so far (burstiness)
    "is_new_tool_for_session",# 1 if this tool hasn't been used yet this session
    "arg_length",             # length of the serialized arguments (payload size)
    "out_of_scope_keyword_hits",  # count of suspicious keywords in the args
    "repeat_tool_streak",     # consecutive identical-tool calls just before this one
]


@dataclass
class SessionState:
    """Rolling state Leash keeps per agent session to compute behavioral features."""
    start_time: float = field(default_factory=time.time)
    tool_history: list[str] = field(default_factory=list)
    call_timestamps: list[float] = field(default_factory=list)

    def record(self, tool_name: str, at: float | None = None) -> None:
        self.tool_history.append(tool_name)
        self.call_timestamps.append(time.time() if at is None else at)


def _out_of_scope_hits(arguments: dict[str, Any]) -> int:
    blob = " ".join(str(v) for v in arguments.values()).lower()
    return sum(1 for kw in OUT_OF_SCOPE_KEYWORDS if kw in blob)


def _repeat_streak(history: list[str], tool_name: str) -> int:
    streak = 0
    for t in reversed(history):
        if t == tool_name:
            streak += 1
        else:
            break
    return streak


def extract_features(
    tool_name: str,
    arguments: dict[str, Any],
    step_index: int,
    session: SessionState,
    max_expected_steps: int = 12,
    now: float | None = None,
) -> dict[str, float]:
    """`now` is injectable (defaults to wall-clock time) so synthetic data
    generation and unit tests can produce deterministic, controllable
    timing-based features without real sleeps."""
    if now is None:
        now = time.time()
    elapsed = now - session.start_time

    recent_window = [t for t in session.call_timestamps if now - t < 10]
    call_rate = len(recent_window) / 10.0

    is_new_tool = 1.0 if tool_name not in session.tool_history else 0.0
    arg_blob = " ".join(f"{k}={v}" for k, v in arguments.items())

    features = {
        "tool_sensitivity": float(TOOL_SENSITIVITY.get(tool_name, DEFAULT_TOOL_SENSITIVITY)),
        "step_index_norm": min(step_index / max_expected_steps, 1.0),
        "seconds_since_start": elapsed,
        "call_rate": call_rate,
        "is_new_tool_for_session": is_new_tool,
        "arg_length": float(len(arg_blob)),
        "out_of_scope_keyword_hits": float(_out_of_scope_hits(arguments)),
        "repeat_tool_streak": float(_repeat_streak(session.tool_history, tool_name)),
    }
    return features


def feature_vector(features: dict[str, float]) -> list[float]:
    """Fixed ordering, used everywhere a model/array expects a plain vector."""
    return [features[name] for name in FEATURE_NAMES]
