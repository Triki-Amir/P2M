"""
ocr_service/config.py
──────────────────────
All tuneable settings for the OCR service.
Values can be overridden via environment variables.
"""

import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

# Root of the whole project (two levels up from this file)
PROJECT_ROOT = Path(__file__).parent.parent

# Shared data folder where event JSON files are read/written
DATA_DIR = PROJECT_ROOT / "data"

# Temp folder for page images during processing (cleaned up after each run)
TEMP_DIR = PROJECT_ROOT / "temp"

# ── PDF rendering ─────────────────────────────────────────────────────────────

# DPI used when rasterising PDF pages to PNG.
# 300 gives good OCR accuracy; lower (150) is faster for large documents.
PDF_DPI: int = int(os.getenv("OCR_PDF_DPI", "300"))

# ── Layout / label filtering ──────────────────────────────────────────────────

# PaddleOCR VL block labels we want to keep.
# Everything else (header, footer, page numbers, watermarks) is discarded.
ALLOWED_LABELS: set[str] = {
    "paragraph_title",
    "text",
    "table",
    "figure_title",
}

# Mapping from PaddleOCR internal labels → our semantic type enum.
LABEL_MAP: dict[str, str] = {
    "paragraph_title": "heading",
    "text":            "paragraph",
    "table":           "table",
    "figure_title":    "figure_caption",
}

# ── Event names ───────────────────────────────────────────────────────────────

OUTPUT_EVENT: str = "ocr_completed"
