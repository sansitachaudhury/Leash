import os
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "10"))
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))
API_MAX_RETRIES = int(os.getenv("API_MAX_RETRIES", "3"))
STORE_PATH = os.path.join(os.path.dirname(__file__), "storage", "runs.json")

DESTRUCTIVE_TOOLS = {"approve_transaction", "delete_file"}
TOOL_SENSITIVITY = {
    "read_email": 0.15,
    "read_document": 0.10,
    "search_web": 0.10,
    "search_database": 0.35,
    "send_email": 0.55,
    "approve_transaction": 0.95,
    "delete_file": 0.90,
}
