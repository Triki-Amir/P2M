"""
ocr_service/config.py
──────────────────────
All tuneable settings for the OCR service.
Values can be overridden via environment variables.
"""

import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
TEMP_DIR     = PROJECT_ROOT / "temp"

# ── PDF rendering ─────────────────────────────────────────────────────────────

PDF_DPI: int = int(os.getenv("OCR_PDF_DPI", "96"))

# ── Layout / label filtering ──────────────────────────────────────────────────

# PaddleOCR VL block labels we want to keep.
# Dropped intentionally:
#   figure_title  → figures are not useful for AO text retrieval
#   header/footer → navigation artefacts, not content
#   page_number   → noise
ALLOWED_LABELS: set[str] = {
    "paragraph_title",   # section / article heading  (H1-level)
    "sub_heading",       # sub-section heading        (H2/H3-level)
    "text",              # body paragraph
    "table",             # tabular data  (PaddleOCR returns HTML; we convert to TSV)
    "table_title",       # caption above/below a table → injected as table.context
}

# Mapping from PaddleOCR internal labels → our normalised semantic type.
# The NLP service reads these types to decide chunking strategy.
LABEL_MAP: dict[str, str] = {
    "paragraph_title": "heading",
    "sub_heading":     "sub_heading",
    "text":            "paragraph",
    "table":           "table",
    "table_title":     "table_caption",   # kept for context injection, not stored standalone
}

# Block types that can supply context text to the table that follows them.
# Used by the context-injection pass in paddle_ocr.py.
TABLE_CONTEXT_TYPES: set[str] = {"paragraph", "table_caption"}

# ── Event names ───────────────────────────────────────────────────────────────

OUTPUT_EVENT: str = "ocr_completed"

# ── RabbitMQ ──────────────────────────────────────────────────────────────────
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://admin:secretpassword@localhost/")
EVENT_EXCHANGE = os.getenv("EVENT_EXCHANGE", "p2m_events")
OCR_QUEUE      = os.getenv("OCR_QUEUE",     "ocr_queue")
NLP_QUEUE      = os.getenv("NLP_QUEUE",     "nlp_queue")
MAX_WORKERS    = int(os.getenv("MAX_WORKERS", "2"))
MAX_RETRY      = int(os.getenv("MAX_RETRY",  "3"))
OCR_TIMEOUT    = int(os.getenv("OCR_TIMEOUT","300"))   # seconds