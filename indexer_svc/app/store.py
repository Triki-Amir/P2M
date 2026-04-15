"""
indexer_svc/app/store.py
========================
PostgreSQL / pgvector persistence for the indexer.

Responsibilities
----------------
- Manage the DB connection
- Resolve doc_id (filename) → document UUID from the documents table
- Upsert chunks with both dense and sparse vectors

pgvector wire formats
---------------------
  vector     : '[0.12, -0.34, ...]'
  sparsevec  : '{1:0.12,305:0.87}/250002'   (1-based indices)
"""

from __future__ import annotations

import logging
from typing import List, Dict, Optional

import psycopg2
import psycopg2.extras

from indexer_svc.app.embedder import ChunkEmbedding
from shared.models import NlpChunk

logger = logging.getLogger(__name__)

SPARSE_DIM = 250002   # bge-m3 vocabulary size


def _to_dense_str(vec) -> str:
    """numpy array → pgvector vector string."""
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


def _to_sparse_str(sparse: Dict[int, float]) -> str:
    """
    {token_id: weight} → pgvector sparsevec string.
    pgvector uses 1-based indices.
    """
    if not sparse:
        return f"{{}}/{SPARSE_DIM}"
    entries = ",".join(
        f"{idx + 1}:{weight:.6f}"
        for idx, weight in sorted(sparse.items())
    )
    return f"{{{entries}}}/{SPARSE_DIM}"


class VectorStore:
    """
    Manages pgvector connection and chunk upserts.

    Usage (context manager recommended):
        with VectorStore(dsn=config.DB_DSN) as store:
            store.upsert_chunks(chunks, embeddings, doc_id)
    """

    def __init__(self, dsn: str):
        self.dsn  = dsn
        self._con = None
        self._cur = None

    def connect(self):
        logger.info("[store] Connecting to PostgreSQL…")
        self._con = psycopg2.connect(self.dsn)
        self._cur = self._con.cursor()
        self._ensure_schema()
        logger.info("[store] Connected.")

    def _ensure_schema(self):
        """
        Ensure pgvector and chunks table exist.

        This prevents runtime failures when the database volume was initialized
        before 02_chunks.sql was added.
        """
        ddl = """
            CREATE EXTENSION IF NOT EXISTS vector;

            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id        TEXT PRIMARY KEY,
                doc_id          TEXT NOT NULL,
                document_id     UUID REFERENCES documents(id) ON DELETE CASCADE,
                page_index      INTEGER NOT NULL,
                block_index     INTEGER NOT NULL,
                chunk_index     INTEGER NOT NULL,
                block_type      TEXT NOT NULL,
                source_lang     TEXT NOT NULL,
                text_original   TEXT NOT NULL,
                text_en         TEXT NOT NULL,
                section_title   TEXT,
                context         TEXT,
                translation_failed BOOLEAN DEFAULT FALSE,
                bbox            FLOAT[],
                dense_vec       vector(1024),
                sparse_vec      sparsevec(250002),
                indexed_at      TIMESTAMPTZ DEFAULT now()
            );

            CREATE INDEX IF NOT EXISTS chunks_dense_hnsw
                ON chunks
                USING hnsw (dense_vec vector_ip_ops)
                WITH (m = 16, ef_construction = 64);

            CREATE INDEX IF NOT EXISTS chunks_sparse_hnsw
                ON chunks
                USING hnsw (sparse_vec sparsevec_ip_ops)
                WITH (m = 16, ef_construction = 64);

            CREATE INDEX IF NOT EXISTS ix_chunks_document_id ON chunks (document_id);
            CREATE INDEX IF NOT EXISTS ix_chunks_doc_id      ON chunks (doc_id);
            CREATE INDEX IF NOT EXISTS ix_chunks_block_type  ON chunks (block_type);
            CREATE INDEX IF NOT EXISTS ix_chunks_source_lang ON chunks (source_lang);
        """
        try:
            self._cur.execute(ddl)
            self._con.commit()
            logger.info("[store] Schema check complete (chunks ready).")
        except Exception:
            self._con.rollback()
            raise

    def close(self):
        if self._cur:
            self._cur.close()
        if self._con:
            self._con.close()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    # ------------------------------------------------------------------
    # Document UUID resolution
    # ------------------------------------------------------------------

    def resolve_document(self, doc_id: str) -> tuple[Optional[str], Optional[str]]:
        """
        Look up the UUID and tenant_id of the document whose filename matches *doc_id*.

        Returns (document_id, tenant_id) or (None, None).
        """
        self._cur.execute(
            "SELECT id, tenant_id FROM documents WHERE filename = %s AND is_deleted = false LIMIT 1",
            (doc_id,),
        )
        row = self._cur.fetchone()
        if row:
            logger.info("[store] Resolved '%s' → document UUID %s", doc_id, row[0])
            return str(row[0]), str(row[1])

        logger.warning(
            "[store] Document '%s' not found in documents table. "
            "Chunks will be stored without a document_id FK.",
            doc_id,
        )
        return None, None

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    def upsert_chunks(
        self,
        chunks: List[NlpChunk],
        embeddings: List[ChunkEmbedding],
        doc_id: str,
    ) -> tuple[int, Optional[str], Optional[str]]:
        """
        Insert or update all chunks in one transaction.

        Returns (number of rows upserted, document_id, tenant_id)
        """
        document_id, tenant_id = self.resolve_document(doc_id)

        # Build embedding lookup map
        emb_map = {e.chunk_id: e for e in embeddings}

        rows = []
        for chunk in chunks:
            emb = emb_map.get(chunk.chunk_id)
            if emb is None:
                logger.warning("[store] No embedding for chunk %s — skipped", chunk.chunk_id)
                continue

            rows.append((
                chunk.chunk_id,
                doc_id,
                document_id,
                chunk.page_index,
                chunk.block_index,
                chunk.chunk_index,
                chunk.block_type,
                chunk.source_lang,
                chunk.text_original,
                chunk.text_en,
                _to_dense_str(emb.dense_vec),
                _to_sparse_str(emb.sparse_vec),
            ))

        if not rows:
            logger.warning("[store] No rows to upsert.")
            return 0

        sql = """
                INSERT INTO chunks (
                    chunk_id, doc_id, document_id,
                    page_index, block_index, chunk_index,
                    block_type, source_lang,
                    text_original, text_en,
                    dense_vec, sparse_vec
                ) VALUES (
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s::vector, %s::sparsevec
                )
                ON CONFLICT (chunk_id) DO UPDATE SET
                    doc_id             = EXCLUDED.doc_id,
                    document_id        = EXCLUDED.document_id,
                    page_index         = EXCLUDED.page_index,
                    block_index        = EXCLUDED.block_index,
                    chunk_index        = EXCLUDED.chunk_index,
                    block_type         = EXCLUDED.block_type,
                    source_lang        = EXCLUDED.source_lang,
                    text_original      = EXCLUDED.text_original,
                    text_en            = EXCLUDED.text_en,
                    dense_vec          = EXCLUDED.dense_vec,
                    sparse_vec         = EXCLUDED.sparse_vec,
                    indexed_at         = now()
            """

        psycopg2.extras.execute_batch(self._cur, sql, rows, page_size=100)
        self._con.commit()

        logger.info("[store] Upserted %d chunks for '%s'.", len(rows), doc_id)
        return len(rows), document_id, tenant_id
