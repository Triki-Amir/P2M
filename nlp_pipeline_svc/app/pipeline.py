import hashlib
from typing import List
from shared.models import OcrDocument, NlpDocument, NlpChunk
from nlp_pipeline_svc.app.nlp.cleaning import clean_text
from nlp_pipeline_svc.app.nlp.chunker import chunk_text
from nlp_pipeline_svc.app.nlp.language_detection import detect_language
from nlp_pipeline_svc.app.nlp.translation import translate_to_en

class NlpOrcestrator:
    def __init__(self, max_chunk_size: int = 500, chunk_overlap: int = 50):
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap

    def process_document(self, ocr_doc: OcrDocument) -> NlpDocument:
        """
        Processes an OCR document: cleans, detects lang, translates, and chunks.
        """
        nlp_chunks = []
        
        for page in ocr_doc.pages:
            for block_index, block in enumerate(page.blocks):
                # 1. Clean Text
                cleaned_text = clean_text(block.text)
                if not cleaned_text:
                    continue
                
                # 2. Detect Language
                source_lang = detect_language(cleaned_text)
                
                # 3. Translate to English (for embedding space)
                translated_text = translate_to_en(cleaned_text, source_lang)
                
                # 4. Chunking (if needed)
                text_chunks = chunk_text(translated_text, self.max_chunk_size, self.chunk_overlap)
                
                for chunk_index, chunk in enumerate(text_chunks):
                    # Generate unique ID
                    chunk_id_raw = f"{ocr_doc.doc_id}:{page.page_index}:{block_index}:{chunk_index}:{chunk}"
                    chunk_id = hashlib.md5(chunk_id_raw.encode("utf-8")).hexdigest()
                    
                    nlp_chunk = NlpChunk(
                        chunk_id=chunk_id,
                        page_index=page.page_index,
                        block_index=block_index,
                        chunk_index=chunk_index,
                        block_type=block.type,
                        source_lang=source_lang,
                        text_original=cleaned_text, # Or the original if cleaned
                        text_en=chunk,
                        bbox=block.bbox
                    )
                    nlp_chunks.append(nlp_chunk)
                    
        return NlpDocument(
            doc_id=ocr_doc.doc_id,
            source_lang=ocr_doc.source_lang,
            chunks=nlp_chunks
        )
