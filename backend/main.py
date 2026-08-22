"""
Leash backend: FastAPI + WebSocket.

Two ways to run a session, same event protocol either way:
  - POST /api/session/start        -> live Groq agent loop (needs GROQ_API_KEY)
  - POST /api/session/replay       -> offline canned trace through the real scorer
Both stream Event objects over  ws://<host>/ws/{session_id}

Frontend flow:
  1. open the websocket for a session_id (any client-generated string)
  2. POST to /api/session/start or /api/session/replay with that session_id
  3. render events as they arrive
"""
from __future__ import annotations
import asyncio
import logging
import uuid
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.agent.groq_agent import run_agent_loop
from backend.agent.replay_engine import run_replay, available_scenarios
from backend.models.schemas import Event, EventType
from backend.security.anomaly_model import get_model
from backend.security.semantic_drift import get_scorer as get_semantic_scorer
from backend.config import GROQ_API_KEY

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("leash.main")

app = FastAPI(title="Leash", description="Runtime Security for AI Agents")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon prototype: dashboard is opened as a local file / any origin
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, session_id: str, ws: WebSocket):
        await ws.accept()
        self.active[session_id] = ws

    def disconnect(self, session_id: str):
        self.active.pop(session_id, None)

    async def send(self, session_id: str, event: Event):
        ws = self.active.get(session_id)
        if ws is None:
            logger.warning("No active websocket for session %s, dropping event %s",
                            session_id, event.type)
            return
        await ws.send_json(event.model_dump(mode="json"))


manager = ConnectionManager()


def _map_event(session_id: str, raw: dict[str, Any]) -> Event:
    kind = raw.pop("_event")
    type_map = {
        "session_start": EventType.SESSION_START,
        "action_proposed": EventType.ACTION_PROPOSED,
        "action_scored": EventType.ACTION_SCORED,
        "action_allowed": EventType.ACTION_ALLOWED,
        "action_blocked": EventType.ACTION_BLOCKED,
        "action_result": EventType.ACTION_RESULT,
        "incident_report": EventType.INCIDENT_REPORT,
        "agent_message": EventType.AGENT_MESSAGE,
        "task_complete": EventType.TASK_COMPLETE,
        "error": EventType.ERROR,
    }
    return Event(type=type_map[kind], session_id=session_id, data=raw)


async def _stream(session_id: str, agen):
    try:
        async for raw in agen:
            event = _map_event(session_id, raw)
            await manager.send(session_id, event)
    except Exception as e:  # noqa: BLE001
        logger.exception("Session %s crashed", session_id)
        await manager.send(session_id, Event(
            type=EventType.ERROR, session_id=session_id, data={"message": str(e)}
        ))


class StartRequest(BaseModel):
    session_id: str
    task: str
    scenario: str | None = None  # "document_injection" | "tool_output_injection" | None


class ReplayRequest(BaseModel):
    session_id: str
    scenario: str = "document_injection"


@app.get("/api/health")
async def health():
    model = get_model()
    return {
        "status": "ok",
        "groq_configured": bool(GROQ_API_KEY),
        "anomaly_model_ready": model.is_ready(),
        "semantic_backend": get_semantic_scorer().backend_name,
        "replay_scenarios": available_scenarios(),
    }


@app.post("/api/session/start")
async def start_session(req: StartRequest):
    """Kicks off a LIVE agent run against the Groq API. The session_id must
    already have an open websocket connection (connect first, then POST)."""
    asyncio.create_task(_stream(req.session_id, run_agent_loop(
        req.session_id, req.task, req.scenario
    )))
    return {"started": True, "session_id": req.session_id, "mode": "live"}


@app.post("/api/session/replay")
async def start_replay(req: ReplayRequest):
    """Kicks off the offline replay — no external API required."""
    asyncio.create_task(_stream(req.session_id, run_replay(req.session_id, req.scenario)))
    return {"started": True, "session_id": req.session_id, "mode": "replay"}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await manager.connect(session_id, websocket)
    try:
        while True:
            # Frontend doesn't need to send anything; keep the socket open.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(session_id)


@app.post("/api/session/new")
async def new_session_id():
    return {"session_id": str(uuid.uuid4())[:8]}
