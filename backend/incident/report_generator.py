from __future__ import annotations
import uuid
from typing import Any

from backend.models.schemas import IncidentReport, ScoreResult, Verdict
from backend.security.explainer import explanation_summary

RECOMMENDATIONS = {
    Verdict.BLOCK: (
        "Action blocked before execution. Review the triggering context (recent "
        "tool outputs / documents read) for a possible prompt injection, then "
        "either resume the task manually or restart the session."
    ),
    Verdict.REVIEW: (
        "Action was allowed but flagged. Spot-check the result; consider lowering "
        "the review threshold for this tool if false positives are frequent."
    ),
    Verdict.ALLOW: "No action needed.",
}


def generate_report(
    session_id: str,
    task: str,
    step: int,
    tool_name: str,
    arguments: dict[str, Any],
    result: ScoreResult,
) -> IncidentReport:
    return IncidentReport(
        incident_id=str(uuid.uuid4())[:8],
        session_id=session_id,
        task=task,
        step=step,
        tool_name=tool_name,
        arguments=arguments,
        verdict=result.verdict,
        risk_score=result.risk_score,
        explanation=explanation_summary(result.top_contributions, result.verdict.value),
        top_contributions=result.top_contributions,
        recommended_action=RECOMMENDATIONS[result.verdict],
    )
