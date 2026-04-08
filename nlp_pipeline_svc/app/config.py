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
