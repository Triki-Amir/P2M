"""
pipeline.py  –  NLP Orchestrator
"""

import hashlib
import logging
from collections import Counter
from typing import List, Optional

from shared.models import OcrDocument, NlpDocument, NlpChunk, OcrBlock
from nlp_pipeline_svc.app.nlp.cleaning import clean_text
from nlp_pipeline_svc.app.nlp.chunker import chunk_block, ChunkConfig
from nlp_pipeline_svc.app.nlp.language_detection import detect_languages
from nlp_pipeline_svc.app.nlp.translation import translate_to_en
from nlp_pipeline_svc.app.nlp.metadata_extractor import extract_metadata

logger = logging.getLogger(__name__)


class NlpOrchestrator:

    def __init__(
        self,
        max_chunk_chars: int = 1200,
        max_chunk_size: int = None,
        similarity_threshold: float = 0.75,
        min_sentences: int = 3,
        fallback_overlap: int = 100,
        chunk_overlap: int = None,
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

    def process_document(self, ocr_doc: OcrDocument) -> NlpDocument:
        nlp_chunks: List[NlpChunk] = []
        lang_votes: List[str] = []

        doc_meta = extract_metadata(ocr_doc)
        global_block_index = 0

        for page in ocr_doc.pages:
            for block in page.blocks:

                if not block.is_nlp_relevant:
                    global_block_index += 1    # ← count skipped blocks too
                    continue

                cleaned = clean_text(block.plain_text)
                if not cleaned:
                    global_block_index += 1    # ← count empty blocks too
                    continue

                source_langs = detect_languages(cleaned)
                lang_votes.extend(source_langs)

                translated   = translate_to_en(cleaned, source_langs)
                primary_lang = source_langs[0]

                translation_failed = (
                    translated.strip() == cleaned.strip()
                    and primary_lang not in ("en", "unknown")
                )

                text_chunks = chunk_block(
                    text=translated,
                    block_type=block.content_type,
                    cfg=self.cfg,
                )

                base_metadata = self._build_metadata(block, translation_failed)

                for chunk_index, chunk in enumerate(text_chunks):
                    nlp_chunks.append(
                        NlpChunk(
                            chunk_id=self._make_chunk_id(
                                ocr_doc.doc_id,
                                page.page_index,
                                global_block_index,
                                chunk_index,
                                chunk,
                            ),
                            page_index    = page.page_index,
                            block_index   = global_block_index,
                            chunk_index   = chunk_index,
                            block_type    = block.block_label,
                            source_lang   = primary_lang,
                            text_original = cleaned,
                            text_en       = chunk,
                            metadata      = base_metadata,
                        )
                    )

                global_block_index += 1    # ← INSIDE block loop, OUTSIDE chunk loop

        doc_lang: Optional[str] = (
            Counter(lang_votes).most_common(1)[0][0] if lang_votes else None
        )

        return NlpDocument(
            doc_id=ocr_doc.doc_id,
            source_lang=doc_lang,
            doc_metadata=doc_meta,
            chunks=nlp_chunks,
            
        )

    @staticmethod
    def _build_metadata(
        block: OcrBlock,
        translation_failed: bool = False,
    ) -> dict:
        return {
            "section_title":      block.section_title,
            "context":            block.context,
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


NlpOrcestrator = NlpOrchestrator