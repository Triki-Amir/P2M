"""
OCR utility module.
Downloads PDFs from MinIO, converts pages to images,
and extracts text using Tesseract for Arabic, French, and English.
"""
import os
import tempfile
from io import BytesIO

from minio import Minio
from minio.error import S3Error
from pdf2image import convert_from_bytes
import pytesseract
from PIL import Image


def get_minio_client() -> Minio:
    """Create and return a configured MinIO client."""
    return Minio(
        os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "admin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "password123"),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
    )


def download_pdf_from_minio(storage_path: str, bucket: str = None) -> bytes:
    """
    Download a PDF file from MinIO.

    Args:
        storage_path: The object key in the MinIO bucket.
        bucket: The bucket name. Defaults to MINIO_BUCKET env var.

    Returns:
        The raw PDF bytes.
    """
    bucket = bucket or os.getenv("MINIO_BUCKET", "pdf-storage")
    client = get_minio_client()

    response = client.get_object(bucket, storage_path)
    try:
        pdf_bytes = response.read()
    finally:
        response.close()
        response.release_conn()

    return pdf_bytes


def pdf_bytes_to_images(pdf_bytes: bytes) -> list:
    """
    Convert PDF bytes into a list of PIL Image objects (one per page).

    Args:
        pdf_bytes: Raw bytes of the PDF file.

    Returns:
        A list of PIL Image objects.
    """
    images = convert_from_bytes(pdf_bytes)
    return images


def extract_text_from_images(images: list, languages: str = "ara+fra+eng") -> dict:
    """
    Run Tesseract OCR on a list of images and return the extracted text.

    Args:
        images: A list of PIL Image objects (one per page).
        languages: Tesseract language codes joined by '+'.
                   Defaults to 'ara+fra+eng' for Arabic, French, and English.

    Returns:
        A dict with 'pages' (list of per-page text) and 'full_text' (combined).
    """
    pages_text = []
    for page_num, image in enumerate(images, start=1):
        text = pytesseract.image_to_string(image, lang=languages)
        pages_text.append({"page": page_num, "text": text.strip()})

    full_text = "\n\n".join(p["text"] for p in pages_text if p["text"])

    return {
        "pages": pages_text,
        "full_text": full_text,
        "page_count": len(images),
    }


def run_ocr_on_document(storage_path: str, language_hint: str = None) -> dict:
    """
    Full OCR pipeline: download PDF from MinIO, convert to images,
    and extract text in Arabic, French, and English.

    Args:
        storage_path: The object key of the PDF in the MinIO bucket.
        language_hint: Optional language hint from the document record.
                       If provided, it is prepended to the default languages
                       so Tesseract prioritises it.

    Returns:
        A dict containing extracted text, page count, and per-page results.
    """
    # Build Tesseract language string
    default_langs = ["ara", "fra", "eng"]
    if language_hint and language_hint not in default_langs:
        default_langs.insert(0, language_hint)
    lang_str = "+".join(default_langs)

    # 1. Download PDF from MinIO
    pdf_bytes = download_pdf_from_minio(storage_path)

    # 2. Convert PDF to images
    images = pdf_bytes_to_images(pdf_bytes)

    # 3. Extract text
    result = extract_text_from_images(images, languages=lang_str)
    result["languages"] = lang_str

    return result
