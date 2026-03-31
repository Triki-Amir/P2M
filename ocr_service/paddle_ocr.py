"""
ocr_service/paddle_ocr.py
──────────────────────────
Wraps PaddleOCR VL pipeline.
All knowledge of PaddleOCR's API lives here — no other file imports paddleocr.
Swap this file to use a different OCR engine (Tesseract, Azure, AWS Textract)
without touching anything else.
"""

from __future__ import annotations
import hashlib
import re
from pathlib import Path
from bs4 import BeautifulSoup
from paddleocr import PaddleOCRVL

from ocr_service.config import ALLOWED_LABELS, LABEL_MAP
from shared.models import OcrBlock, OcrPage

# Initialise once at import time — loading the model is expensive.
_pipeline: PaddleOCRVL | None = None


def _get_pipeline() -> PaddleOCRVL:
    global _pipeline
    if _pipeline is None:
        print("  [paddle_ocr] loading PaddleOCRVL model…")
        _pipeline = PaddleOCRVL()
    return _pipeline


# ── Text helpers ──────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _table_html_to_tsv(html: str) -> str:
    """Strip HTML table markup → plain TSV rows for the NLP service."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        rows.append("\t".join(cells))
    return "\n".join(rows)


def _clean_content(label: str, raw_content: str) -> str:
    if LABEL_MAP.get(label) == "table":
        return _table_html_to_tsv(raw_content)
    return _normalize(raw_content)


# ── Core OCR ──────────────────────────────────────────────────────────────────

def ocr_image(image_path: Path, page_index: int) -> OcrPage:
    """
    Run PaddleOCR VL on a single page image.

    Args:
        image_path:  path to the PNG rendered from the PDF page
        page_index:  zero-based page number (for the output model)

    Returns:
        OcrPage with all valid, deduplicated blocks.
    """
    pipeline = _get_pipeline()
    output   = pipeline.predict(str(image_path))

    seen_hashes: set[str] = set()
    blocks: list[OcrBlock] = []

    for res in output:
        # PaddleOCRVLResult is a dict subclass; data lives in .json["res"]
        raw = res.json["res"]

        for item in raw.get("parsing_res_list", []):
            label   = item.get("block_label", "")
            content = item.get("block_content", "")
            bbox    = item.get("block_bbox")

            # Drop unwanted block types
            if label not in ALLOWED_LABELS:
                continue

            text = _clean_content(label, content)
            if not text:
                continue

            # Deduplicate within this page
            h = hashlib.md5(text.encode()).hexdigest()
            if h in seen_hashes:
                continue
            seen_hashes.add(h)

            blocks.append(OcrBlock(
                type=LABEL_MAP[label],
                text=text,
                bbox=bbox,
            ))

    return OcrPage(page_index=page_index, blocks=blocks)
