"""
ocr_service/main.py
────────────────────
Entry point for the OCR service.

Usage:
    python -m ocr_service.main path/to/document.pdf

This file only orchestrates — no business logic lives here.
Each step is delegated to its own module.
"""

from __future__ import annotations
import sys
from pathlib import Path

from ocr_service.pdf_to_images import pdf_to_images, cleanup_images
from ocr_service.paddle_ocr import ocr_image, ocr_pdf_via_api
from ocr_service.output_writer import write_output


def run(pdf_path: str | Path) -> None:
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc_id = pdf_path.name
    print(f"\n[ocr_service] starting — {doc_id}")

    # Step 1: Try API first (sends PDF directly, no image conversion needed)
    pages = ocr_pdf_via_api(pdf_path)

    if pages is not None:
        # API succeeded — skip image conversion entirely
        print(f"[ocr_service] API returned {len(pages)} page(s)")

    else:
        # Step 1b: API failed → render PDF pages to images
        print("[ocr_service] falling back to local model…")
        image_paths = pdf_to_images(pdf_path)

        # Step 2: OCR each page image with local model
        pages = []
        for page_index, image_path in enumerate(image_paths):
            print(f"[ocr_service] processing page {page_index + 1}/{len(image_paths)}")
            page = ocr_image(image_path, page_index)
            pages.append(page)

        # Step 3: clean up temp images (only created in fallback path)
        cleanup_images(image_paths)

    # Step 4: publish ocr_completed event
    out_path = write_output(doc_id=doc_id, pages=pages, file_size=pdf_path.stat().st_size)

    print(f"[ocr_service] done -> {out_path}\n")
    return [p.dict() for p in pages]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m ocr_service.main <path_to_pdf>")
        sys.exit(1)

    run(sys.argv[1])