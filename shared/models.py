"""
shared/models.py
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
    type: str = Field(
        description="Semantic type: heading | paragraph | table | figure_caption"
    )
    text: str = Field(
        description="Cleaned text content of the block"
    )
    bbox: Optional[list[float]] = Field(
        default=None,
        description="Bounding box [x1, y1, x2, y2] in original image pixels"
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
    block_type: str
    source_lang: str = Field(description="Detected language of the original text")
    text_original: str = Field(description="Original text before translation")
    text_en: str = Field(description="English text used for embedding")
    metadata: dict = Field(
        default_factory=dict,
        description="Extracted fields: dates, budgets, orgs, locations, etc."
    )
    bbox: Optional[list[float]] = None


class NlpDocument(BaseModel):
    """
    Output of the NLP service / payload of the nlp_completed event.
    This is what indexer_service reads as input.
    """
    doc_id: str
    source_lang: Optional[str] = None
    chunks: list[NlpChunk]
