import sys
from pathlib import Path

# Add project root to sys.path so we can import 'shared'
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from typing import Optional

from shared import event_bus
from shared.models import OcrDocument
from nlp_pipeline_svc.app.pipeline import NlpOrcestrator
from nlp_pipeline_svc.app import config

def run_consumer() -> Optional[object]:
    """
    Main loop for the NLP service.
    Consumes ocr_completed event, runs the pipeline, and publishes nlp_completed.
    
    This implementation follows the pattern in shared/event_bus.py (disk-based).
    """
    print(f"[nlp_service] Watching for {config.INPUT_EVENT} in {config.DATA_DIR}...")
    
    # ── Orchestrator ───────────────────────────
    orchestrator = NlpOrcestrator(
        max_chunk_chars=config.MAX_CHUNK_CHARS,
        fallback_overlap=config.CHUNK_OVERLAP,
    )

    try:
        # Load the OCR results
        ocr_doc = event_bus.consume(config.INPUT_EVENT, OcrDocument, config.DATA_DIR)
        
        print(f"[nlp_service] Processing doc: {ocr_doc.doc_id}")
        
        # Run the NLP pipeline
        nlp_doc = orchestrator.process_document(ocr_doc)
        
        print(f"[nlp_service] Generated {len(nlp_doc.chunks)} semantic chunks.")
        
        # Publish the results
        event_bus.publish(config.OUTPUT_EVENT, nlp_doc, config.DATA_DIR)
        
        print("[nlp_service] DONE.")
        return nlp_doc

    except FileNotFoundError:
        print(f"[nlp_service] Error: {config.INPUT_EVENT}.json not found in {config.DATA_DIR}.")
        print("[nlp_service] Ensure the OCR service runs first.")
        return None
    except Exception as e:
        print(f"[nlp_service] Error during processing: {e}")
        return None

if __name__ == "__main__":
    run_consumer()
