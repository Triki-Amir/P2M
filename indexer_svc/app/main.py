"""
indexer_svc/app/main.py
=======================
Entry point for the indexer service.

Workflow
--------
  1. Read nlp_completed.json from the shared data folder
  2. Embed every chunk (text_en) with bge-m3 → dense + sparse vectors
  3. Resolve doc_id (filename) → document UUID from documents table
  4. Upsert all vectors + metadata into pgvector chunks table
"""

import sys
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from shared import event_bus
from shared.models import NlpDocument
from indexer_svc.app.embedder import Embedder
from indexer_svc.app.store import VectorStore
from indexer_svc.app import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run_indexer() -> int:
    logger.info(
        "[indexer] Watching for '%s' in %s…",
        config.INPUT_EVENT, config.DATA_DIR,
    )

    # 1. Load NlpDocument ─────────────────────────────────────────────────
    try:
        nlp_doc: NlpDocument = event_bus.consume(
            config.INPUT_EVENT, NlpDocument, config.DATA_DIR
        )
    except FileNotFoundError:
        logger.error(
            "[indexer] %s.json not found in %s. Run NLP service first.",
            config.INPUT_EVENT, config.DATA_DIR,
        )
        return 0

    logger.info(
        "[indexer] Doc '%s' — %d chunks to index.",
        nlp_doc.doc_id, len(nlp_doc.chunks),
    )

    if not nlp_doc.chunks:
        logger.warning("[indexer] No chunks — nothing to index.")
        return 0

    # 2. Embed ────────────────────────────────────────────────────────────
    embedder  = Embedder(config.EMBEDDING_MODEL, config.EMBED_BATCH_SIZE)
    texts     = [c.text_en  for c in nlp_doc.chunks]
    chunk_ids = [c.chunk_id for c in nlp_doc.chunks]

    embeddings = embedder.embed(texts, chunk_ids)
    logger.info("[indexer] %d embeddings generated.", len(embeddings))

    # 3 & 4. Resolve UUID + upsert ────────────────────────────────────────
    with VectorStore(dsn=config.DB_DSN) as store:
        n, document_id, tenant_id = store.upsert_chunks(
            chunks=nlp_doc.chunks,
            embeddings=embeddings,
            doc_id=nlp_doc.doc_id,
        )

    logger.info("[indexer] Done — %d chunks indexed for '%s'.", n, nlp_doc.doc_id)
    
    # 5. Trigger compliance service via RabbitMQ event
    if document_id and tenant_id:
        try:
            # We import the publisher only if needed
            from indexer_svc.publisher import trigger_compliance_task
            trigger_compliance_task(document_id, tenant_id)
        except Exception as e:
            logger.error("[indexer] Failed to trigger compliance task: %s", e)

    return n


if __name__ == "__main__":
    run_indexer()
