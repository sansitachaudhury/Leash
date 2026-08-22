"""
Shared data contracts between the agent loop, the scorer, and the frontend.
Every object that crosses the WebSocket is one of the Event subtypes below,
serialized with `.model_dump(mode="json")`.
"""
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Verdict(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"


class TaskStartRequest(BaseModel):
    task: str = Field(..., description="The task/instruction the agent is given.")
    scenario: Optional[str] = Field(
        None, description="Optional canned scenario id to inject a hijack for the demo."
    )


class ToolCallProposal(BaseModel):
    """What the agent wants to do, before Leash has looked at it."""
    step: int
    tool_name: str
    arguments: dict[str, Any]
    agent_thought: str = ""  # the agent's stated reasoning for this call, if any


class FeatureContribution(BaseModel):
    feature: str
    value: float
    contribution: float  # signed SHAP-style contribution to the risk score
    description: str


class ScoreResult(BaseModel):
    semantic_similarity: float  # 0-1, similarity of this action to the task
    semantic_drift_score: float  # 0-100, higher = more drifted
    anomaly_score: float  # 0-100, higher = more behaviorally anomalous
    sensitivity_score: float  # 0-100, static sensitivity of the tool/args
    risk_score: float  # 0-100 final blended score
    verdict: Verdict
    top_contributions: list[FeatureContribution] = Field(default_factory=list)
    raw_features: dict[str, float] = Field(default_factory=dict)


class IncidentReport(BaseModel):
    incident_id: str
    session_id: str
    timestamp: str = Field(default_factory=now_iso)
    task: str
    step: int
    tool_name: str
    arguments: dict[str, Any]
    verdict: Verdict
    risk_score: float
    explanation: str
    top_contributions: list[FeatureContribution]
    recommended_action: str


class EventType(str, Enum):
    SESSION_START = "session_start"
    ACTION_PROPOSED = "action_proposed"
    ACTION_SCORED = "action_scored"
    ACTION_ALLOWED = "action_allowed"
    ACTION_BLOCKED = "action_blocked"
    ACTION_RESULT = "action_result"
    INCIDENT_REPORT = "incident_report"
    AGENT_MESSAGE = "agent_message"
    TASK_COMPLETE = "task_complete"
    ERROR = "error"


class Event(BaseModel):
    type: EventType
    session_id: str
    timestamp: str = Field(default_factory=now_iso)
    data: dict[str, Any] = Field(default_factory=dict)
