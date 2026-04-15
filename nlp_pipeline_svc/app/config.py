import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

# Root of the whole project (three levels up from this file)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Shared data folder where event JSON files are read/written
DATA_DIR = PROJECT_ROOT / "data"

# ── NLP Settings ──────────────────────────────────────────────────────────────

# Target language for translation (unified embedding space)
TARGET_LANG: str = os.getenv("NLP_TARGET_LANG", "en")

# Chunking settings
# config.py  — replace old names with new ones
MAX_CHUNK_CHARS = 1200   # was MAX_CHUNK_SIZE
CHUNK_OVERLAP   = 100    # unchanged, but now maps to fallback_overlap
# ── Event names ───────────────────────────────────────────────────────────────

INPUT_EVENT: str = "ocr_completed"
OUTPUT_EVENT: str = "nlp_completed"

# ── RabbitMQ ──────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()
RABBITMQ_URL = os.getenv("RABBITMQ_URL")
EVENT_EXCHANGE = os.getenv("EVENT_EXCHANGE", "p2m_events")
NLP_QUEUE      = os.getenv("NLP_QUEUE",      "nlp_queue")
INDEXER_QUEUE  = os.getenv("INDEXER_QUEUE",  "indexer_queue")
MAX_WORKERS    = int(os.getenv("MAX_WORKERS", "2"))
MAX_RETRY      = int(os.getenv("MAX_RETRY",  "3"))
NLP_TIMEOUT    = int(os.getenv("NLP_TIMEOUT","300"))