"""
pipeline.py  –  NLP Orchestrator
=================================
Cleans → detects language → translates → chunks each OCR block using the
block-type-aware chunker.

Key behaviours
--------------
- block.section_title and block.context are promoted into NlpChunk.metadata
  so they are available at retrieval time without fetching adjacent chunks.
- Translation is applied to the *whole block* before chunking so the semantic
  chunker operates in a single language (English) and embeddings are consistent.
- NlpDocument.source_lang is set via majority vote over all block detections
  (ocr_doc.source_lang is unreliable — OCR service leaves it as None).
- translation_failed flag is set in metadata when translate_to_en returns the
  input unchanged for a non-English block (silent passthrough detection).
"""

import hashlib
import logging
from collections import Counter
from typing import List, Optional

from shared.models import OcrDocument, NlpDocument, NlpChunk, OcrBlock
from nlp_pipeline_svc.app.nlp.cleaning import clean_text
from nlp_pipeline_svc.app.nlp.chunker import chunk_block, ChunkConfig
from nlp_pipeline_svc.app.nlp.language_detection import detect_language
from nlp_pipeline_svc.app.nlp.translation import translate_to_en

logger = logging.getLogger(__name__)


class NlpOrchestrator:
    """
    Orchestrates the full NLP pipeline for one OcrDocument.

    Chunking strategy (delegated to chunker.chunk_block):
        heading / sub_heading / table / table_caption → atomic  (1 chunk)
        paragraph (list pattern detected)             → list    (1 chunk)
        paragraph (prose)                             → semantic (N chunks)
    """

    def __init__(
        self,
        max_chunk_chars: int = 1200,
        max_chunk_size: int = None,    # legacy alias
        similarity_threshold: float = 0.75,
        min_sentences: int = 3,
        fallback_overlap: int = 100,
        chunk_overlap: int = None,     # legacy alias
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        if max_chunk_size is not None:
            max_chunk_chars = max_chunk_size
        if chunk_overlap is not None:
            fallback_overlap = chunk_overlap

        self.cfg = ChunkConfig(
            similarity_threshold=similarity_threshold,
            min_sentences=min_sentences,
            max_chunk_chars=max_chunk_chars,
            fallback_overlap=fallback_overlap,
            embedding_model=embedding_model,
        )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def process_document(self, ocr_doc: OcrDocument) -> NlpDocument:
        """
        Process every block in every page of *ocr_doc*.

        Pipeline per block:
          1. Clean text
          2. Detect language  (Arabic Unicode check → French markers → "en")
          3. Translate whole block to English
          4. Chunk (strategy depends on block.type)
          5. Build NlpChunk objects with metadata
        After all blocks:
          6. Set NlpDocument.source_lang via majority vote
        """
        nlp_chunks: List[NlpChunk] = []
        lang_votes: List[str] = []

        for page in ocr_doc.pages:
            for block_index, block in enumerate(page.blocks):

                # 1. Clean ────────────────────────────────────────────────
                cleaned = clean_text(block.text)
                if not cleaned:
                    continue

                # 2. Detect language ───────────────────────────────────────
                #    Unicode-range check means even single Arabic words like
                #    "ملحق" or "ملاحظة:" are correctly classified now.
                source_lang = detect_language(cleaned)
                lang_votes.append(source_lang)

                # 3. Translate the whole block to English ─────────────────
                translated = translate_to_en(cleaned, source_lang)

                # Flag silent passthroughs (translation model did nothing)
                translation_failed = (
                    translated.strip() == cleaned.strip()
                    and source_lang != "en"
                )
                if translation_failed:
                    logger.warning(
                        "[pipeline] Translation passthrough block %d "
                        "(lang=%s): %r…",
                        block_index, source_lang, cleaned[:60],
                    )

                # 4. Chunk ────────────────────────────────────────────────
                text_chunks = chunk_block(
                    text=translated,
                    block_type=block.type,
                    cfg=self.cfg,
                )

                # 5. Build NlpChunk objects ───────────────────────────────
                base_metadata = self._build_metadata(block, translation_failed)

                for chunk_index, chunk in enumerate(text_chunks):
                    nlp_chunks.append(
                        NlpChunk(
                            chunk_id=self._make_chunk_id(
                                ocr_doc.doc_id,
                                page.page_index,
                                block_index,
                                chunk_index,
                                chunk,
                            ),
                            page_index=page.page_index,
                            block_index=block_index,
                            chunk_index=chunk_index,
                            block_type=block.type,
                            source_lang=source_lang,
                            text_original=cleaned,
                            text_en=chunk,
                            metadata=base_metadata,
                            bbox=block.bbox,
                        )
                    )

        # 6. Document-level language: majority vote ────────────────────────
        doc_lang: Optional[str] = (
            Counter(lang_votes).most_common(1)[0][0] if lang_votes else None
        )

        return NlpDocument(
            doc_id=ocr_doc.doc_id,
            source_lang=doc_lang,
            chunks=nlp_chunks,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_metadata(block: OcrBlock, translation_failed: bool = False) -> dict:
        return {
            "section_title": block.section_title,   # None when absent — expected
            "context": block.context,
            "translation_failed": translation_failed,
        }

    @staticmethod
    def _make_chunk_id(
        doc_id: str,
        page_index: int,
        block_index: int,
        chunk_index: int,
        text: str,
    ) -> str:
        raw = f"{doc_id}:{page_index}:{block_index}:{chunk_index}:{text}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()


# Backward-compatible alias (old code used the typo spelling)
NlpOrcestrator = NlpOrchestrator