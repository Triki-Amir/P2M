"""
ocr_service/output_writer.py
─────────────────────────────
Assembles the final OcrDocument and publishes the ocr_completed event.
Separated from main.py so the serialisation logic is independently testable.
"""

from __future__ import annotations
from pathlib import Path

from shared.models import OcrDocument, OcrPage
from shared import event_bus
from ocr_service.config import DATA_DIR, OUTPUT_EVENT


def write_output(doc_id: str, pages: list[OcrPage]) -> Path:
    """
    Build an OcrDocument from the processed pages and publish it.

    Args:
        doc_id:  original PDF filename used as the document identifier
        pages:   list of OcrPage objects, one per PDF page

    Returns:
        Path to the written JSON event file.
    """
    document = OcrDocument(
        doc_id=doc_id,
        source_lang=None,   # language detection is done by the NLP service
        pages=pages,
    )

    out_path = event_bus.publish(
        event_name=OUTPUT_EVENT,
        payload=document,
        data_dir=DATA_DIR,
    )

    total_blocks = sum(len(p.blocks) for p in pages)
    print(f"  [output_writer] {len(pages)} page(s), {total_blocks} block(s) → {out_path}")

    return out_path
