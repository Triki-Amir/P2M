"""
P2M/shared/models.py
─────────────────
Pydantic schemas shared across all services.
These are the contracts between OCR → NLP → Indexer.
Never add service-specific logic here.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── OCR output ────────────────────────────────────────────────────────────────

class OcrBlock(BaseModel):
    """One detected layout block from a single PDF page."""

    block_id: int = Field(
        description="Original block ID from PaddleOCR, unique within its page."
    )
    reading_order: Optional[int] = Field(
        default=None,
        description=(
            "Reading order position within the page. "
            "None for blocks excluded from reading flow (headers, footers, images)."
        )
    )
    block_label: str = Field(
        description=(
            "Raw layout label from PaddleOCR: text | paragraph_title | doc_title | "
            "table | image | header | footer | footnote | aside_text | seal | ..."
        )
    )
    content_type: str = Field(
        description=(
            "Mapped semantic type: body_text | title | table | image | "
            "header | footer | aside | page_number | footnote | seal"
        )
    )
    is_nlp_relevant: bool = Field(
        description=(
            "False for blocks in the OCR markdown_ignore_labels list "
            "(header, footer, footnote, page_number, aside_text). "
            "The NLP service skips these blocks entirely."
        )
    )
    plain_text: str = Field(
        description=(
            "Cleaned text content — markdown syntax and HTML tags stripped. "
            "Empty string for image blocks."
        )
    )
    languages: list[str] = Field(
        description=(
            "Detected ISO 639-1 codes, e.g. ['en'], ['hi', 'en']. "
            "'unknown' if no recognisable script is found."
        )
    )
    section_title: Optional[str] = Field(
        default=None,
        description=(
            "Breadcrumb of the nearest heading(s) above this block on the page. "
            "Format: 'Heading > Sub-heading'."
        )
    )
    context: Optional[str] = Field(
        default=None,
        description=(
            "For table blocks only: plain text of the paragraph immediately "
            "preceding this table."
        )
    )


class OcrPage(BaseModel):
    """All blocks extracted from one PDF page."""
    page_index: int
    blocks: list[OcrBlock]


class OcrDocument(BaseModel):
    """
    Output of the OCR service / payload of the ocr_completed event.
    This is what nlp_service reads as input.
    """
    doc_id: str = Field(description="Original filename, e.g. 'tender_2025.pdf'")
    source_lang: Optional[str] = Field(
        default=None,
        description="Detected dominant language: 'fr' | 'ar' | 'en' | None"
    )
    pages: list[OcrPage]


# ── NLP output ────────────────────────────────────────────────────────────────

class NlpChunk(BaseModel):
    """
    One semantic chunk produced by the NLP service.
    This is the atomic unit the Indexer embeds and stores.
    """
    chunk_id: str = Field(description="MD5 of page:block:chunk:text")
    page_index: int
    block_index: int
    chunk_index: int
    block_type: str = Field(
        description=(
            "Semantic content type carried over from OcrBlock.content_type: "
            "body_text | title | table | image | ..."
        )
    )
    source_lang: str = Field(description="Detected language of the original text")
    text_original: str = Field(description="Original text before translation")
    text_en: str = Field(description="English text used for embedding")
    



class NlpDocument(BaseModel):
    doc_id: str
    source_lang: Optional[str] = None
    doc_metadata: dict = Field(
        default_factory=dict,
        description=(
            "Document-level metadata extracted before chunking. "
            "Keys: title, nit_number, organization, client, location, "
            "deadline (ISO 8601), budget, contact_email, contact_phone."
        ),
    )
    chunks: list[NlpChunk]