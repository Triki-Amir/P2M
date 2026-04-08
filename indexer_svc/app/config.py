"""
indexer_svc/app/config.py
=========================
All settings for the indexer service.
Override any value via environment variables in production.
"""

import os
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────

# Shared data folder — same convention as NLP service
DATA_DIR    = Path(os.getenv("DATA_DIR", r"C:\P2M\data"))
INPUT_EVENT = "nlp_completed"          # reads nlp_completed.json

# ── PostgreSQL / pgvector ─────────────────────────────────────────────────

DB_HOST     = os.getenv("DB_HOST",     "localhost")
DB_PORT     = int(os.getenv("DB_PORT", "5432"))
DB_NAME     = os.getenv("DB_NAME",     "postgres")
DB_USER     = os.getenv("DB_USER",     "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "123456789")

DB_DSN = (
    f"host={DB_HOST} port={DB_PORT} "
    f"dbname={DB_NAME} user={DB_USER} password={DB_PASSWORD}"
)

# ── Embedding ─────────────────────────────────────────────────────────────

EMBEDDING_MODEL  = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
DENSE_DIM        = 1024       # bge-m3 dense output dimension
SPARSE_VOCAB_DIM = 250002     # bge-m3 tokenizer vocabulary size
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "16"))
