"""
ocr_service/pdf_to_images.py
─────────────────────────────
Converts each page of a PDF into a PNG image.
Isolated here so it can be swapped for a different renderer
(e.g. Poppler, Ghostscript) without touching any other file.
"""

from __future__ import annotations
from pathlib import Path
import fitz  # PyMuPDF
from ocr_service.config import PDF_DPI, TEMP_DIR


def pdf_to_images(pdf_path: str | Path) -> list[Path]:
    """
    Render every page of a PDF to a PNG file.

    Args:
        pdf_path: path to the input PDF

    Returns:
        Ordered list of Paths to the generated PNG files.
        Caller is responsible for deleting them after use.
    """
    pdf_path = Path(pdf_path)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    image_paths: list[Path] = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix  = page.get_pixmap(dpi=PDF_DPI)

        out_path = TEMP_DIR / f"page_{page_num:04d}.png"
        pix.save(str(out_path))
        image_paths.append(out_path)

        print(f"  [pdf_to_images] page {page_num + 1}/{len(doc)} → {out_path.name}")

    doc.close()
    return image_paths


def cleanup_images(image_paths: list[Path]) -> None:
    """Delete temporary page images after OCR is complete."""
    for p in image_paths:
        if p.exists():
            p.unlink()
    print(f"  [pdf_to_images] cleaned up {len(image_paths)} temp image(s)")
