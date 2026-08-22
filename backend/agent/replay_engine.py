"""
Demo-safe fallback: replays a canned agent trace through the REAL Leash
scoring pipeline (feature extraction, semantic drift, IsolationForest, SHAP)
— the only thing that's scripted is which tool calls the "agent" proposes,
not how Leash evaluates them. This means the block/allow decisions you see
in replay mode are genuinely computed, not hardcoded, so it's an honest demo
of the pipeline even with the Groq API unavailable.
"""
from __future__ import annotations
import asyncio
import json
import logging
from typing import AsyncIterator, Any

from backend.config import REPLAY_TRACES_PATH
from backend.agent.tools import execute_tool
from backend.security.feature_extractor import SessionState
from backend.security.scorer import score_action
from backend.incident.report_generator import generate_report
from backend.models.schemas import Verdict

logger = logging.getLogger("leash.replay")

STEP_DELAY_SECONDS = 1.1  # paced for a live demo audience, not instant dumping


def available_scenarios() -> list[str]:
    data = json.loads(REPLAY_TRACES_PATH.read_text())
    return list(data.keys())


async def run_replay(session_id: str, scenario: str) -> AsyncIterator[dict[str, Any]]:
    data = json.loads(REPLAY_TRACES_PATH.read_text())
    trace = data.get(scenario)
    if trace is None:
        yield {"_event": "error", "message": f"Unknown replay scenario: {scenario}"}
        return

    task = trace["task"]
    session = SessionState()

    yield {"_event": "session_start", "task": task, "scenario": scenario, "mode": "replay"}
    await asyncio.sleep(STEP_DELAY_SECONDS * 0.5)

    for step, entry in enumerate(trace["steps"]):
        tool_name = entry["tool_name"]
        arguments = entry["arguments"]
        thought = entry.get("agent_thought", "")

        if thought:
            yield {"_event": "agent_message", "content": thought, "step": step}
            await asyncio.sleep(STEP_DELAY_SECONDS * 0.5)

        yield {"_event": "action_proposed", "step": step, "tool_name": tool_name,
               "arguments": arguments}
        await asyncio.sleep(STEP_DELAY_SECONDS * 0.4)

        # Scoring (semantic embeddings, IsolationForest, SHAP) is CPU-bound and
        # synchronous — run it off the event loop so it can't stall other
        # concurrent sessions or the WebSocket keepalive.
        result = await asyncio.to_thread(score_action, task, tool_name, arguments, step, session)

        yield {"_event": "action_scored", "step": step, "tool_name": tool_name,
               "arguments": arguments, "score": result.model_dump(mode="json")}
        await asyncio.sleep(STEP_DELAY_SECONDS * 0.3)

        if result.verdict == Verdict.BLOCK:
            report = generate_report(session_id, task, step, tool_name, arguments, result)
            yield {"_event": "action_blocked", "step": step, "tool_name": tool_name,
                   "arguments": arguments, "score": result.model_dump(mode="json")}
            yield {"_event": "incident_report", "report": report.model_dump(mode="json")}
        else:
            if result.verdict == Verdict.REVIEW:
                report = generate_report(session_id, task, step, tool_name, arguments, result)
                yield {"_event": "incident_report", "report": report.model_dump(mode="json")}
            tool_result = execute_tool(tool_name, arguments)
            yield {"_event": "action_allowed", "step": step, "tool_name": tool_name,
                   "arguments": arguments, "score": result.model_dump(mode="json")}
            yield {"_event": "action_result", "step": step, "tool_name": tool_name,
                   "result": tool_result}

        await asyncio.sleep(STEP_DELAY_SECONDS)

    yield {"_event": "task_complete", "final_message": "(replay finished)", "step": len(trace["steps"])}
