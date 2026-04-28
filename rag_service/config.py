"""
RAG Service Configuration
All tunable parameters for retrieval, generation, and infrastructure.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class RAGSettings(BaseSettings):
    # ── PostgreSQL / pgvector ─────────────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "postgres"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str

    # Table and column names — matched to store.py schema
    CHUNKS_TABLE: str = "chunks"
    CHUNK_ID_COL: str = "chunk_id"
    CHUNK_DOC_ID_COL: str = "document_id"
    CHUNK_TEXT_COL: str = "text_en"
    CHUNK_EMBEDDING_COL: str = "dense_vec"
    EMBEDDING_DIM: int = 1024              # BAAI/bge-m3 dense vector dimension

    # ── Hybrid Retrieval ──────────────────────────────────────────────────
    TOP_K_SEMANTIC: int = 10      # candidates from vector search
    TOP_K_BM25: int = 10          # candidates from full-text search
    TOP_K_FINAL: int = 10          # chunks sent to the LLM after RRF fusion
    RRF_K: int = 60               # RRF constant (60 is standard)

    # ── Ollama / LLM ─────────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "deepseek-v3.1:671b-cloud"
    OLLAMA_TEMPERATURE: float = 0.2
    OLLAMA_TOP_P: float = 0.9
    OLLAMA_MAX_TOKENS: int = 1024
    OLLAMA_TIMEOUT: int = 120

    # ── RAG Prompt ────────────────────────────────────────────────────────
    SYSTEM_PROMPT: str = (
        "You are an expert document analyst. "
        "Answer the user's question using ONLY the context passages provided below. "
        "If the answer is not found in the context, say so clearly — do not hallucinate. "
        "Cite the source passage index [1], [2], etc. when referencing specific information. "
        "Be concise, accurate, and professional."
    )
    MAX_CONTEXT_CHARS: int = 6000

    # ── Memory ────────────────────────────────────────────────────────
    MEMORY_TABLE_NAME: str = "chat_history"
    MEMORY_MAX_EXCHANGES: int = 5      # keep last 5 user+assistant pairs
    # ── WebSocket Server ──────────────────────────────────────────────────
    WS_HOST: str = "0.0.0.0"
    WS_PORT: int = 8001
    WS_PATH: str = "/rag/ws"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache()
def get_settings() -> RAGSettings:
    return RAGSettings()
