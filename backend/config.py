"""
Central configuration for Leash.
All thresholds/weights live here so scoring behavior can be tuned without
touching the scoring logic itself.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

# --- Groq / Agent -----------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", 12))

# --- Leash scoring thresholds (0-100 risk score) -----------------------------
# score >= BLOCK_THRESHOLD          -> blocked before execution
# REVIEW_THRESHOLD <= score < BLOCK -> allowed but flagged for human review
# score < REVIEW_THRESHOLD          -> allowed silently
BLOCK_THRESHOLD = float(os.getenv("LEASH_BLOCK_THRESHOLD", 70))
REVIEW_THRESHOLD = float(os.getenv("LEASH_REVIEW_THRESHOLD", 45))

# --- Feature weighting --------------------------------------------------------
# Final risk score = weighted blend of semantic drift, anomaly score, and the
# static sensitivity of the action itself. Tuned so that a highly sensitive
# action (e.g. wire transfer) can never sneak through purely on "normal-looking"
# behavioral stats, and a low-sensitivity action can't get blocked on drift alone.
WEIGHT_SEMANTIC_DRIFT = 0.40
WEIGHT_ANOMALY = 0.35
WEIGHT_SENSITIVITY = 0.25

# Static sensitivity per tool: how much damage this tool can do if misused.
# 0 = read-only/harmless, 100 = irreversible/high-blast-radius.
TOOL_SENSITIVITY = {
    "search_web": 5,
    "read_file": 10,
    "read_email": 10,
    "query_database": 25,
    "create_calendar_event": 20,
    "write_file": 45,
    "send_email": 55,
    "approve_transaction": 90,
    "transfer_funds": 95,
    "delete_file": 80,
    "grant_access": 85,
    "execute_shell": 95,
}
DEFAULT_TOOL_SENSITIVITY = 50  # unknown tool -> treat as moderately risky

# Keywords that, if found in a tool call's arguments, indicate the action
# targets something outside the normal scope of a task (e.g. an external
# domain, a wildcard, "all" records). Cheap heuristic feature, cheap to extend.
OUT_OF_SCOPE_KEYWORDS = [
    "all", "*", "external", "unknown_vendor", "admin", "root",
    "bypass", "override", "ignore previous", "wire", "unverified",
]

# --- Model artifact paths -----------------------------------------------------
MODEL_DIR = BASE_DIR / "security" / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)
ISOLATION_FOREST_PATH = MODEL_DIR / "isolation_forest.joblib"
SCALER_PATH = MODEL_DIR / "feature_scaler.joblib"
FEATURE_NAMES_PATH = MODEL_DIR / "feature_names.json"

# --- Data paths ---------------------------------------------------------------
DATA_DIR = BASE_DIR / "data"
REPLAY_TRACES_PATH = DATA_DIR / "replay_traces.json"
TRAINING_DATA_PATH = DATA_DIR / "synthetic_training_data.json"
EVAL_DATA_PATH = DATA_DIR / "synthetic_eval_data.json"

# --- Embedding model -----------------------------------------------------------
# Small + fast, fine for local/offline use. semantic_drift.py falls back to a
# TF-IDF cosine-similarity model automatically if this can't be downloaded
# (e.g. no network access), so the demo never hard-fails.
SENTENCE_MODEL_NAME = "all-MiniLM-L6-v2"
