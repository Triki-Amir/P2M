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

from ocr_service.config import ALLOWED_LABELS, LABEL_MAP
from shared.models import OcrBlock, OcrPage

# ── Config ────────────────────────────────────────────────────────────────────

API_URL        = os.environ.get("PADDLE_API_URL",   "https://a4beybi7x2z4r2p6.aistudio-app.com/layout-parsing")
API_TOKEN      = os.environ.get("PADDLE_API_TOKEN", "23e0bc0098f13ea9a1497c67479b2fbee18bc59f")
API_TIMEOUT    = 120  # seconds — PDFs take longer than images

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


# ── Markdown → OcrBlock parser (for API response) ─────────────────────────────

def _markdown_to_blocks(markdown_text: str, page_index: int) -> list[OcrBlock]:
    """
    Parse the markdown returned by the API into OcrBlock objects.

    Block types mapped:
      # / ## / ###  → heading
      |---|          → table
      everything else → paragraph
    """
    seen_hashes: set[str] = set()
    blocks: list[OcrBlock] = []

    # Split into logical chunks separated by blank lines
    chunks = re.split(r"\n{2,}", markdown_text.strip())

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        # ── Table (markdown pipe syntax) ──────────────────────────────────
        if re.search(r"^\|.+\|$", chunk, re.MULTILINE):
            # Convert markdown table → TSV
            lines = chunk.splitlines()
            rows = []
            for line in lines:
                if re.match(r"^\|[-| :]+\|$", line):
                    continue  # skip separator row
                cells = [c.strip() for c in line.strip("|").split("|")]
                rows.append("\t".join(cells))
            text = "\n".join(rows)
            block_type = "table"

        # ── Heading ───────────────────────────────────────────────────────
        elif chunk.startswith("#"):
            text = re.sub(r"^#+\s*", "", chunk).strip()
            block_type = "heading"

        # ── Paragraph / text ──────────────────────────────────────────────
        else:
            text = _normalize(chunk)
            block_type = "paragraph"

        if not text:
            continue

        # Deduplicate
        h = hashlib.md5(text.encode()).hexdigest()
        if h in seen_hashes:
            continue
        seen_hashes.add(h)

        # Only keep types your downstream pipeline expects
        ocr_type = block_type  # adjust if LABEL_MAP uses different names
        blocks.append(OcrBlock(type=ocr_type, text=text, bbox=None))

    return blocks


# ── Local model block builder (unchanged logic) ───────────────────────────────

def _build_blocks_from_res(parsing_res_list: list) -> list[OcrBlock]:
    seen_hashes: set[str] = set()
    blocks: list[OcrBlock] = []
    for item in parsing_res_list:
        label   = item.get("block_label", "")
        content = item.get("block_content", "")
        bbox    = item.get("block_bbox")
        if label not in ALLOWED_LABELS:
            continue
        if LABEL_MAP.get(label) == "table":
            text = _table_html_to_tsv(content)
        else:
            text = _normalize(content)
        if not text:
            continue
        h = hashlib.md5(text.encode()).hexdigest()
        if h in seen_hashes:
            continue
        seen_hashes.add(h)
        blocks.append(OcrBlock(type=LABEL_MAP[label], text=text, bbox=bbox))
    return blocks


# ── API path ──────────────────────────────────────────────────────────────────

def ocr_pdf_via_api(pdf_path: Path) -> list[OcrPage] | None:
    """
    Send the entire PDF to the API and get back all pages at once.
    Returns list[OcrPage] or None on failure (triggers per-page local fallback).

    Call this INSTEAD of looping ocr_image() when API is available.
    """
    if not API_URL or not API_TOKEN:
        return None

    try:
        print(f"  [paddle_ocr] sending PDF to API: {pdf_path.name}")
        file_data = base64.b64encode(pdf_path.read_bytes()).decode("ascii")

        payload = {
            "file": file_data,
            "fileType": 0,              # 0 = PDF
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
        }
        headers = {
            "Authorization": f"token {API_TOKEN}",
            "Content-Type": "application/json",
        }

        resp = requests.post(API_URL, json=payload, headers=headers, timeout=API_TIMEOUT)
        resp.raise_for_status()

        layout_results = resp.json()["result"]["layoutParsingResults"]
        pages: list[OcrPage] = []

        for page_index, res in enumerate(layout_results):
            markdown_text = res.get("markdown", {}).get("text", "")
            blocks = _markdown_to_blocks(markdown_text, page_index)
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