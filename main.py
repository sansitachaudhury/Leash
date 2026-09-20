"""
Leash - AI Agent Reliability Engine
FastAPI backend with WebSocket live events, scenario generation,
sandbox execution, and result persistence.
"""
import asyncio
import json
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent_spec import AGENT_SPEC
from generator.scenario_generator import generate_scenarios
from runner.sandbox_runner import run_scenario
from core.classifier import classify
from scorecard.scorecard import build_scorecard
from storage.store import save_run, list_runs, get_run, delete_run, get_stats
from log import get_logger

log = get_logger("main")

app = FastAPI(
    title="Leash - AI Agent Reliability Engine",
    description="CI/CD and Sandboxed Safeguards for Autonomous AI Agents",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE = {"scenarios": []}
SETTINGS = {"hardening_mode": False}
INTERVENTIONS = {}
connections: list[WebSocket] = []


async def broadcast(event: dict):
    dead = []
    for ws in connections:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for d in dead:
        connections.remove(d)


@app.websocket("/ws/events")
async def ws_events(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)
    log.info(f"WebSocket connected ({len(connections)} total)")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connections.remove(websocket)
        log.info(f"WebSocket disconnected ({len(connections)} total)")


class GenerateRequest(BaseModel):
    num_scenarios: int = Field(default=12, ge=4, le=30)

class SettingsRequest(BaseModel):
    hardening_mode: bool

class InterveneRequest(BaseModel):
    scenario_id: str
    action: str

class RunSuiteRequest(BaseModel):
    run_label: str = "manual run"

class CustomScenarioRequest(BaseModel):
    title: str
    task: str
    category: str = "benign"
    injection: dict | None = None


@app.post("/api/generate-scenarios")
async def api_generate(req: GenerateRequest):
    log.stage(f"Generating {req.num_scenarios} scenarios")
    scenarios = generate_scenarios(AGENT_SPEC, req.num_scenarios)
    STATE["scenarios"] = scenarios
    log.done(f"Generated {len(scenarios)} scenarios")
    return {"count": len(scenarios), "scenarios": scenarios}


@app.get("/api/scenarios")
async def api_get_scenarios():
    return {"scenarios": STATE["scenarios"]}


@app.post("/api/custom-scenario")
async def api_add_custom_scenario(req: CustomScenarioRequest):
    scenario = {
        "id": f"custom-{len(STATE['scenarios'])}",
        "title": req.title,
        "task": req.task,
        "category": req.category,
        "injection": req.injection,
    }
    STATE["scenarios"].append(scenario)
    return {"scenario": scenario, "total": len(STATE["scenarios"])}


@app.delete("/api/scenarios/{scenario_id}")
async def api_delete_scenario(scenario_id: str):
    original_len = len(STATE["scenarios"])
    STATE["scenarios"] = [s for s in STATE["scenarios"] if s["id"] != scenario_id]
    if len(STATE["scenarios"]) < original_len:
        return {"status": "deleted", "total": len(STATE["scenarios"])}
    raise HTTPException(status_code=404, detail="Scenario not found")


@app.post("/api/settings")
async def api_set_settings(req: SettingsRequest):
    SETTINGS["hardening_mode"] = req.hardening_mode
    return {"settings": SETTINGS}


@app.get("/api/settings")
async def api_get_settings():
    return {"settings": SETTINGS}


@app.post("/api/intervene")
async def api_intervene(req: InterveneRequest):
    if req.scenario_id in INTERVENTIONS:
        INTERVENTIONS[req.scenario_id]["action"] = req.action
        INTERVENTIONS[req.scenario_id]["event"].set()
        return {"status": "ok"}
    return {"error": "no active intervention request found for this scenario"}


@app.post("/api/run-suite")
async def api_run_suite(req: RunSuiteRequest):
    if not STATE["scenarios"]:
        return {"error": "no scenarios generated yet"}
    asyncio.create_task(_execute_suite(req.run_label))
    return {"status": "started", "scenario_count": len(STATE["scenarios"])}


async def _execute_suite(run_label: str):
    total = len(STATE["scenarios"])
    log.stage(f"Running suite {run_label} - {total} scenarios")
    await broadcast({"type": "suite_start", "total": total})
    results = []
    start_time = time.time()

    for i, scenario in enumerate(STATE["scenarios"]):
        log.info(f"[{i + 1}/{total}] Running: {scenario.get('title', scenario['id'])}")
        trace = await run_scenario(scenario, AGENT_SPEC, emit=broadcast, settings=SETTINGS, interventions=INTERVENTIONS)
        classification = classify(trace)
        results.append({"trace": trace, "classification": classification})
        await broadcast({"type": "scenario_classified", "scenario_id": scenario["id"], "classification": classification})

    elapsed = time.time() - start_time
    scorecard = build_scorecard(results, run_label)
    run_id = save_run(scorecard)
    log.done(f"Suite complete - {scorecard['reliability_score']}% reliability ({elapsed:.1f}s)")
    await broadcast({"type": "suite_done", "run_id": run_id, "scorecard": scorecard, "elapsed_seconds": round(elapsed, 2)})


@app.get("/api/runs")
async def api_list_runs():
    return {"runs": list_runs()}


@app.get("/api/runs/{run_id}")
async def api_get_run(run_id: str):
    run = get_run(run_id)
    return run or {"error": "not found"}


@app.delete("/api/runs/{run_id}")
async def api_delete_run(run_id: str):
    if delete_run(run_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Run not found")


@app.get("/api/stats")
async def api_get_stats():
    return get_stats()


@app.get("/api/runs/{run_id}/export")
async def api_export_run(run_id: str, format: str = "json"):
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if format == "csv":
        return _export_csv(run)
    return run


def _export_csv(run: dict) -> StreamingResponse:
    import io, csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["scenario_id", "category", "task", "passed", "failures", "step_count", "max_risk"])
    for s in run.get("scenarios", []):
        writer.writerow([s["id"], s["category"], s["task"][:80], s["passed"], "; ".join(f["category"] for f in s.get("failures", [])), s["step_count"], s.get("max_risk", 0)])
    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode()), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="leash-run-{run["run_id"]}.csv"'})


app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")
