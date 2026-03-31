import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

# Root of the whole project (two levels up from this file)
PROJECT_ROOT = Path(__file__).parent.parent

# Shared data folder where event JSON files are read/written
DATA_DIR = PROJECT_ROOT / "data"

# ── NLP Settings ──────────────────────────────────────────────────────────────

# Target language for translation (unified embedding space)
TARGET_LANG: str = os.getenv("NLP_TARGET_LANG", "en")

# Chunking settings
MAX_CHUNK_SIZE: int = int(os.getenv("NLP_MAX_CHUNK_SIZE", "500"))
CHUNK_OVERLAP: int = int(os.getenv("NLP_CHUNK_OVERLAP", "50"))

# ── Event names ───────────────────────────────────────────────────────────────

INPUT_EVENT: str = "ocr_completed"
OUTPUT_EVENT: str = "nlp_completed"
