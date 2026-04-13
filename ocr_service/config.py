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
# Only excluded: image, figure, chart, seal — pure visual blocks with no text.
ALLOWED_LABELS: set[str] = {
    "paragraph_title",   # section heading
    "sub_heading",       # sub-section heading
    "doc_title",         # document-level title (cover page)
    "text",              # body paragraph
    "table",             # tabular data
    "table_title",       # table caption
    "header",            # page header — may contain org name, doc ref
    "footer",            # page footer — may contain NIT number, dates
    "footnote",          # footnotes — may contain legal references
    "aside_text",        # side annotations
    "number",            # page numbers (kept for position context)
    "reference",         # bibliographic references
}

# Mapping from PaddleOCR labels → normalised semantic type.
# The NLP service reads content_type to decide chunking strategy.
LABEL_MAP: dict[str, str] = {
    "paragraph_title": "title",
    "sub_heading":     "title",
    "doc_title":       "title",
    "text":            "body_text",
    "table":           "table",
    "table_title":     "title",
    "header":          "header",
    "footer":          "footer",
    "footnote":        "footer",
    "aside_text":      "aside",
    "number":          "page_number",
    "reference":       "body_text",
}

# ── NLP relevance filter ──────────────────────────────────────────────────────

# Blocks with these labels are passed to OCR output but skipped by the
# NLP chunker (not embedded, not stored as chunks).
# They are still read by the metadata extractor before chunking.
NLP_IGNORED_LABELS: set[str] = {
    "number",       # page numbers add no semantic value to chunks
    "image",        # no text
    "figure",       # no text
    "chart",        # no text
    "seal",         # no text
}

# ── Block types that can supply context to the table that follows ─────────────

TABLE_CONTEXT_TYPES: set[str] = {"body_text", "title"}

# ── Event names ───────────────────────────────────────────────────────────────

OUTPUT_EVENT: str = "ocr_completed"

# ── RabbitMQ ──────────────────────────────────────────────────────────────────

RABBITMQ_URL   = os.getenv("RABBITMQ_URL")
EVENT_EXCHANGE = os.getenv("EVENT_EXCHANGE", "p2m_events")
OCR_QUEUE      = os.getenv("OCR_QUEUE",      "ocr_queue")
NLP_QUEUE      = os.getenv("NLP_QUEUE",      "nlp_queue")
MAX_WORKERS    = int(os.getenv("MAX_WORKERS", "2"))
MAX_RETRY      = int(os.getenv("MAX_RETRY",  "3"))
OCR_TIMEOUT    = int(os.getenv("OCR_TIMEOUT","300"))