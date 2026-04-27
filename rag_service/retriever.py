"""
RAG Service — Hybrid Retriever
Combines pgvector inner product (semantic) with PostgreSQL tsvector BM25
(keyword) search, then fuses results using Reciprocal Rank Fusion (RRF).
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import asyncpg

from .config import RAGSettings
from .models import SourceChunk

logger = logging.getLogger(__name__)


@dataclass
class RawChunk:
    chunk_id: str
    document_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    semantic_rank: int | None = None
    bm25_rank: int | None = None
    rrf_score: float = 0.0


class HybridRetriever:
    """
    Performs hybrid retrieval over pgvector + PostgreSQL full-text search.

    Flow:
        1. Embed the query using the same embedding model used during indexing.
        2. Run vector inner product search via pgvector (<#> operator).
        3. Run BM25 keyword search via PostgreSQL tsvector / tsquery.
        4. Fuse both ranked lists with Reciprocal Rank Fusion (RRF).
        5. Return top-k SourceChunk objects.
    """

    def __init__(self, settings: RAGSettings, embed_fn):
        """
        Args:
            settings:  RAGSettings instance.
            embed_fn:  Async callable (query: str) -> list[float].
                       Must produce vectors of dimension settings.EMBEDDING_DIM.
                       Must use BAAI/bge-m3 — same model the Indexer used.
        """
        self.cfg = settings
        self.embed_fn = embed_fn
        self.pool: asyncpg.Pool | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Create the asyncpg connection pool."""
        self.pool = await asyncpg.create_pool(
            host=self.cfg.POSTGRES_HOST,
            port=self.cfg.POSTGRES_PORT,
            database=self.cfg.POSTGRES_DB,
            user=self.cfg.POSTGRES_USER,
            password=self.cfg.POSTGRES_PASSWORD,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        logger.info("HybridRetriever: asyncpg pool created.")

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            logger.info("HybridRetriever: pool closed.")

    # ── Public API ────────────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        document_id: str,
    ) -> list[SourceChunk]:
        """
        Main entry point. Returns fused, ranked SourceChunk list.
        """
        logger.info(f"HybridRetriever running search for query: '{query}'")
        # 1. Embed query
        query_vector = await self.embed_fn(query)
        vector_str = self._format_vector(query_vector)

        async with self.pool.acquire() as conn:
            # 2. Semantic search
            semantic_rows = await self._semantic_search(conn, vector_str, document_id)

            # 3. BM25 keyword search
            bm25_rows = await self._bm25_search(conn, query, document_id)

        # 4. RRF fusion
        fused = self._reciprocal_rank_fusion(semantic_rows, bm25_rows)

        # 5. Build SourceChunk list
        return [
            SourceChunk(
                chunk_id=str(chunk.chunk_id),
                document_id=str(chunk.document_id),
                content=chunk.content,
                score=round(chunk.rrf_score, 4),
                metadata=chunk.metadata or {},
            )
            for chunk in fused[: self.cfg.TOP_K_FINAL]
        ]

    # ── Semantic Search ───────────────────────────────────────────────────────

    async def _semantic_search(
        self,
        conn: asyncpg.Connection,
        vector_str: str,
        document_id: str,
    ) -> list[RawChunk]:
        """
        Uses pgvector's <#> inner product operator.
        Matches the HNSW index built with vector_ip_ops in store.py.
        <#> returns negative inner product → lower value = more similar → ORDER BY ASC.
        """
        sql = f"""
            SELECT
                {self.cfg.CHUNK_ID_COL}         AS chunk_id,
                {self.cfg.CHUNK_DOC_ID_COL}      AS document_id,
                {self.cfg.CHUNK_TEXT_COL}         AS content,
                page_index,
                block_type,
                ({self.cfg.CHUNK_EMBEDDING_COL} <#> $1::vector) AS distance
            FROM {self.cfg.CHUNKS_TABLE}
            WHERE {self.cfg.CHUNK_DOC_ID_COL} = $2
            ORDER BY distance ASC
            LIMIT $3
        """
        rows = await conn.fetch(sql, vector_str, document_id, self.cfg.TOP_K_SEMANTIC)
        return [
            RawChunk(
                chunk_id=str(r["chunk_id"]),
                document_id=str(r["document_id"]),
                content=r["content"],
                metadata={
                    "page_index": r["page_index"],
                    "block_type": r["block_type"],
                },
                semantic_rank=idx + 1,
            )
            for idx, r in enumerate(rows)
        ]

    # ── BM25 / Full-Text Search ───────────────────────────────────────────────

    async def _bm25_search(
        self,
        conn: asyncpg.Connection,
        query: str,
        document_id: str,
    ) -> list[RawChunk]:
        """
        Uses PostgreSQL tsvector + ts_rank_cd for BM25-style keyword scoring.
        Falls back gracefully if no keyword matches are found.
        """
        sql = f"""
            SELECT
                {self.cfg.CHUNK_ID_COL}         AS chunk_id,
                {self.cfg.CHUNK_DOC_ID_COL}      AS document_id,
                {self.cfg.CHUNK_TEXT_COL}         AS content,
                page_index,
                block_type,
                ts_rank_cd(
                    to_tsvector('english', {self.cfg.CHUNK_TEXT_COL}),
                    plainto_tsquery('english', $1)
                ) AS bm25_score
            FROM {self.cfg.CHUNKS_TABLE}
            WHERE
                {self.cfg.CHUNK_DOC_ID_COL} = $2
                AND to_tsvector('english', {self.cfg.CHUNK_TEXT_COL})
                    @@ plainto_tsquery('english', $1)
            ORDER BY bm25_score DESC
            LIMIT $3
        """
        try:
            rows = await conn.fetch(sql, query, document_id, self.cfg.TOP_K_BM25)
        except Exception as exc:
            logger.warning("BM25 search failed (continuing with semantic only): %s", exc)
            return []

        return [
            RawChunk(
                chunk_id=str(r["chunk_id"]),
                document_id=str(r["document_id"]),
                content=r["content"],
                metadata={
                    "page_index": r["page_index"],
                    "block_type": r["block_type"],
                },
                bm25_rank=idx + 1,
            )
            for idx, r in enumerate(rows)
        ]

    # ── Reciprocal Rank Fusion ────────────────────────────────────────────────

    def _reciprocal_rank_fusion(
        self,
        semantic: list[RawChunk],
        bm25: list[RawChunk],
    ) -> list[RawChunk]:
        """
        RRF score = Σ 1 / (k + rank_i)
        Merges both lists, deduplicates by chunk_id, sorts by descending RRF score.
        """
        k = self.cfg.RRF_K
        scores: dict[str, float] = {}
        chunks: dict[str, RawChunk] = {}

        for chunk in semantic:
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + (
                1.0 / (k + (chunk.semantic_rank or 999))
            )
            chunks[chunk.chunk_id] = chunk

        for chunk in bm25:
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + (
                1.0 / (k + (chunk.bm25_rank or 999))
            )
            if chunk.chunk_id not in chunks:
                chunks[chunk.chunk_id] = chunk

        for cid, score in scores.items():
            chunks[cid].rrf_score = score

        return sorted(chunks.values(), key=lambda c: c.rrf_score, reverse=True)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _format_vector(vec: list[float]) -> str:
        """Format a Python list as a pgvector literal string: '[0.1, 0.2, ...]'"""
        return "[" + ",".join(f"{v:.8f}" for v in vec) + "]"
