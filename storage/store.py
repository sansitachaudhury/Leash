"""
Persistent storage for run results.
Uses JSON file with cross-platform file locking for safe concurrent access.
"""
import json
import os
import time
import uuid
import platform
import config
from log import get_logger

log = get_logger("storage")

# Cross-platform file locking
if platform.system() != "Windows":
    import fcntl

    def _lock_file(fd):
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _unlock_file(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)
else:
    import msvcrt

    def _lock_file(fd):
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def _unlock_file(fd):
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


def _ensure_file():
    os.makedirs(os.path.dirname(config.STORE_PATH), exist_ok=True)
    if not os.path.exists(config.STORE_PATH):
        with open(config.STORE_PATH, "w") as f:
            json.dump([], f)


def _read_runs() -> list:
    _ensure_file()
    with open(config.STORE_PATH, "r") as f:
        return json.load(f)


def save_run(scorecard: dict) -> str:
    """Save a scorecard to persistent storage. Returns the run ID."""
    run_id = str(uuid.uuid4())[:8]
    record = {"run_id": run_id, "timestamp": time.time(), **scorecard}

    _ensure_file()
    fd = os.open(config.STORE_PATH, os.O_RDWR | os.O_CREAT, 0o666)
    try:
        _lock_file(fd)
        with os.fdopen(fd, "r") as f:
            runs = json.load(f)
        runs.append(record)
        with open(config.STORE_PATH, "w") as f:
            json.dump(runs, f, indent=2)
    finally:
        try:
            _unlock_file(fd)
        except Exception:
            pass

    log.info(f"Saved run {run_id}")
    return run_id


def list_runs() -> list[dict]:
    """List all runs, sorted by timestamp."""
    runs = _read_runs()
    return sorted(runs, key=lambda r: r.get("timestamp", 0))


def get_run(run_id: str) -> dict | None:
    """Get a specific run by ID."""
    for r in list_runs():
        if r["run_id"] == run_id:
            return r
    return None


def delete_run(run_id: str) -> bool:
    """Delete a specific run by ID."""
    fd = os.open(config.STORE_PATH, os.O_RDWR | os.O_CREAT, 0o666)
    try:
        _lock_file(fd)
        with os.fdopen(fd, "r") as f:
            runs = json.load(f)
        original_len = len(runs)
        runs = [r for r in runs if r["run_id"] != run_id]
        if len(runs) < original_len:
            with open(config.STORE_PATH, "w") as f:
                json.dump(runs, f, indent=2)
            log.info(f"Deleted run {run_id}")
            return True
        return False
    finally:
        try:
            _unlock_file(fd)
        except Exception:
            pass


def get_stats() -> dict:
    """Get aggregate statistics across all runs."""
    runs = list_runs()
    if not runs:
        return {"total_runs": 0, "avg_score": 0, "best_score": 0, "worst_score": 0}

    scores = [r.get("reliability_score", 0) for r in runs]
    return {
        "total_runs": len(runs),
        "avg_score": round(sum(scores) / len(scores), 1),
        "best_score": max(scores),
        "worst_score": min(scores),
        "first_run": runs[0].get("timestamp"),
        "last_run": runs[-1].get("timestamp"),
    }
