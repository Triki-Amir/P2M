-- 02_chunks.sql
-- Indexer service schema.
-- Runs after 01_documents.sql so the FK to documents.id is valid.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    -- ── Identity ──────────────────────────────────────────────────────
    chunk_id        TEXT            PRIMARY KEY,

    -- FK to the ingestion pipeline's documents table.
    -- doc_id stores the filename (e.g. "subo.pdf") used throughout the
    -- NLP pipeline. document_id is the UUID that joins to documents.id.
    doc_id          TEXT            NOT NULL,
    document_id     UUID            REFERENCES documents(id) ON DELETE CASCADE,

    -- ── Position in source document ───────────────────────────────────
    page_index      INTEGER         NOT NULL,
    block_index     INTEGER         NOT NULL,
    chunk_index     INTEGER         NOT NULL,

    -- ── Classification ────────────────────────────────────────────────
    block_type      TEXT            NOT NULL,
    source_lang     TEXT            NOT NULL,

    -- ── Text content ──────────────────────────────────────────────────
    text_original   TEXT            NOT NULL,   -- source language
    text_en         TEXT            NOT NULL,   -- English (what was embedded)

    -- ── Context metadata (promoted from OcrBlock) ─────────────────────
    section_title   TEXT,                       -- breadcrumb heading, nullable
    context         TEXT,                       -- preceding paragraph for tables
    translation_failed BOOLEAN      DEFAULT FALSE,

    -- ── Spatial ───────────────────────────────────────────────────────
    bbox            FLOAT[],                    -- [x1, y1, x2, y2]

    -- ── Vectors ───────────────────────────────────────────────────────
    -- bge-m3 dense output: 1024 dimensions, L2-normalised
    dense_vec       vector(1024),

    -- bge-m3 sparse output: weighted lexical terms
    -- vocabulary size of bge-m3 tokenizer = 250002
    sparse_vec      sparsevec(250002),

    -- ── Timestamps ────────────────────────────────────────────────────
    indexed_at      TIMESTAMPTZ     DEFAULT now()
);

-- ── Indexes ───────────────────────────────────────────────────────────────

-- Dense ANN — HNSW with inner product (= cosine on normalised bge-m3 vectors)
CREATE INDEX IF NOT EXISTS chunks_dense_hnsw
    ON chunks
    USING hnsw (dense_vec vector_ip_ops)
    WITH (m = 16, ef_construction = 64);

-- Sparse ANN — HNSW for lexical dot-product retrieval
CREATE INDEX IF NOT EXISTS chunks_sparse_hnsw
    ON chunks
    USING hnsw (sparse_vec sparsevec_ip_ops)
    WITH (m = 16, ef_construction = 64);

-- Metadata indexes for filtered search
CREATE INDEX IF NOT EXISTS ix_chunks_document_id ON chunks (document_id);
CREATE INDEX IF NOT EXISTS ix_chunks_doc_id      ON chunks (doc_id);
CREATE INDEX IF NOT EXISTS ix_chunks_block_type  ON chunks (block_type);
CREATE INDEX IF NOT EXISTS ix_chunks_source_lang ON chunks (source_lang);
