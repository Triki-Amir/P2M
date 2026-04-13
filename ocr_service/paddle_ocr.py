"""
ocr_service/paddle_ocr.py
──────────────────────────
Primary:   PaddleOCR VL 1.5 cloud API  (free, 20k pages/day)
           Accepts PDF directly → skips pdf_to_images when API is used.
Fallback:  Local PaddleOCRVL model     (GPU, processes page images)
"""

from __future__ import annotations
import hashlib
import os
import re
import base64
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from paddleocr import PaddleOCRVL

from ocr_service.config import ALLOWED_LABELS, LABEL_MAP, NLP_IGNORED_LABELS
from shared.models import OcrBlock, OcrPage

# ── Config ────────────────────────────────────────────────────────────────────

API_URL     = os.environ.get("PADDLE_API_URL")
API_TOKEN   = os.environ.get("PADDLE_API_TOKEN")
API_TIMEOUT = 120  # seconds — PDFs take longer than images

# ── Local model (lazy-loaded fallback) ────────────────────────────────────────

_pipeline: PaddleOCRVL | None = None


def _get_pipeline() -> PaddleOCRVL:
    global _pipeline
    if _pipeline is None:
        print("  [paddle_ocr] loading local PaddleOCRVL model (fallback)…")
        _pipeline = PaddleOCRVL(pipeline_version="v1")
    return _pipeline


# ── Text helpers ──────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _table_html_to_tsv(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        rows.append("\t".join(cells))
    return "\n".join(rows)


# ── Shared block builder (API + local model) ──────────────────────────────────

MARKDOWN_IGNORED = {
    "header_image", "footer_image",
}


def _build_blocks_from_res(parsing_res_list: list) -> list[OcrBlock]:
    from nlp_pipeline_svc.app.nlp.language_detection import detect_languages

    seen_hashes: set[str] = set()
    blocks: list[OcrBlock] = []

    for idx, item in enumerate(parsing_res_list):
        label   = item.get("block_label", "")
        content = item.get("block_content", "")

        if label not in ALLOWED_LABELS:
            continue

        if LABEL_MAP.get(label) == "table":
            plain = _table_html_to_tsv(content)
        else:
            plain = _normalize(content)

        if not plain:
            continue

        h = hashlib.md5(plain.encode()).hexdigest()
        if h in seen_hashes:
            continue
        seen_hashes.add(h)

        blocks.append(OcrBlock(
            block_id        = idx,
            reading_order   = item.get("block_order"),   # ← block_index removed
            block_label     = label,
            content_type    = LABEL_MAP.get(label, "body_text"),
            is_nlp_relevant = label not in NLP_IGNORED_LABELS,
            plain_text      = plain,
            languages       = detect_languages(plain),
            section_title   = None,
            context         = None,
        ))

    return blocks

# ── API path ──────────────────────────────────────────────────────────────────

def ocr_pdf_via_api(pdf_path: Path) -> list[OcrPage] | None:
    """
    Send the entire PDF to the cloud API and get back all pages at once.
    Uses parsing_res_list from the API response directly — same structure
    as the local model output, so _build_blocks_from_res handles both.

    Returns list[OcrPage] or None on failure (triggers local model fallback).
    """
    if not API_URL or not API_TOKEN:
        return None

    try:
        print(f"  [paddle_ocr] sending PDF to API: {pdf_path.name}")
        file_data = base64.b64encode(pdf_path.read_bytes()).decode("ascii")

        payload = {
            "file":                      file_data,
            "fileType":                  0,       # 0 = PDF
            "useDocOrientationClassify": False,
            "useDocUnwarping":           False,
            "useChartRecognition":       False,
        }
        headers = {
            "Authorization": f"token {API_TOKEN}",
            "Content-Type":  "application/json",
        }

        resp = requests.post(API_URL, json=payload, headers=headers, timeout=API_TIMEOUT)
        resp.raise_for_status()

        layout_results = resp.json()["result"]["layoutParsingResults"]
        pages: list[OcrPage] = []

        for page_index, res in enumerate(layout_results):
            parsing_res_list = res.get("prunedResult", {}).get("parsing_res_list", [])
            blocks = _build_blocks_from_res(parsing_res_list)
            pages.append(OcrPage(page_index=page_index, blocks=blocks))
            print(f"  [paddle_ocr] page {page_index} → API ✓ ({len(blocks)} blocks)")

        return pages

    except Exception as e:
        print(f"  [paddle_ocr] API failed: {e} → falling back to local model")
        return None


# ── Local fallback (per-page image) ──────────────────────────────────────────

def ocr_image(image_path: Path, page_index: int) -> OcrPage:
    """Local model fallback — called per page image."""
    pipeline = _get_pipeline()
    output   = pipeline.predict(str(image_path))

    parsing_res_list = []
    for res in output:
        parsing_res_list.extend(res.json["res"].get("parsing_res_list", []))

    blocks = _build_blocks_from_res(parsing_res_list)
    print(f"  [paddle_ocr] page {page_index} → local model ({len(blocks)} blocks)")
    return OcrPage(page_index=page_index, blocks=blocks)