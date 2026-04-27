"""
indexer_svc/consumer.py
========================
Indexer Service — Consumer (end of pipeline, no publisher).
Receives document_nlp_completed events from the Indexer queue.
Runs embedding + pgvector storage → updates PostgreSQL status → done.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import aio_pika
from aio_pika import Message, IncomingMessage, connect_robust
from aio_pika.pool import Pool

import indexer_svc.app.config as settings
from indexer_svc.app.embedder import Embedder
from indexer_svc.app.store import VectorStore
from shared.models import NlpChunk
from indexer_svc.publisher import trigger_compliance_task

logger = logging.getLogger(__name__)


class IndexerConsumer:
    """
    Async RabbitMQ consumer for Indexer tasks.
    End of the pipeline — no publisher.

    Flow per message:
        1. Parse payload (document_id, chunks, …)
        2. Update PostgreSQL status → 'indexing'
        3. Embed chunks (BAAI/bge-m3 dense + sparse)
        4. Upsert vectors into pgvector (chunks table)
        5. Update PostgreSQL status → 'indexed' / 'index_failed'
    """

    def __init__(self, db_pool):
        """
        Args:
            db_pool: asyncpg connection pool
        """
        self.db_pool = db_pool
        self.embedder = Embedder()          # lazy-loaded on first use

        self.connection_pool: Optional[Pool] = None
        self.channel_pool: Optional[Pool] = None
        self.consume_channel: Optional[aio_pika.Channel] = None
        self.consumer_tag: Optional[str] = None
        self.running = False

    # ── Connection pools ──────────────────────────────────────────────────────

    async def _create_connection(self) -> aio_pika.RobustConnection:
        return await connect_robust(
            settings.RABBITMQ_URL, timeout=30, reconnect_interval=5
        )

    async def _create_channel(self) -> aio_pika.Channel:
        async with self.connection_pool.acquire() as conn:
            channel = await conn.channel()
            await channel.set_qos(prefetch_count=settings.MAX_WORKERS)
            return channel

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        logger.info("IndexerConsumer: connecting to RabbitMQ at %s", settings.RABBITMQ_URL)
        self.running = True

        self.connection_pool = Pool(self._create_connection, max_size=5)
        self.channel_pool = Pool(self._create_channel, max_size=20)

        self.consume_channel = await self._create_channel()

        # DLX / DLQ
        dlx = await self.consume_channel.declare_exchange(
            f"{settings.INDEXER_QUEUE}.dlx",
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )
        dlq = await self.consume_channel.declare_queue(
            f"{settings.INDEXER_QUEUE}.dlq", durable=True
        )
        await dlq.bind(dlx, routing_key=settings.INDEXER_QUEUE)

        # Main queue
        queue = await self.consume_channel.declare_queue(
            settings.INDEXER_QUEUE,
            durable=True,
            arguments={
                "x-message-ttl": 3_600_000,
                "x-max-length": 10_000,
                "x-dead-letter-exchange": f"{settings.INDEXER_QUEUE}.dlx",
                "x-dead-letter-routing-key": settings.INDEXER_QUEUE,
            },
        )

        self.consumer_tag = await queue.consume(self._on_message, no_ack=False)
        logger.info("IndexerConsumer: listening on '%s'", settings.INDEXER_QUEUE)

    async def stop(self):
        logger.info("IndexerConsumer: shutting down...")
        self.running = False
        try:
            if self.consumer_tag and self.consume_channel:
                await self.consume_channel.cancel(self.consumer_tag)
                await self.consume_channel.close()
        except Exception as exc:
            logger.warning("IndexerConsumer: error cancelling tag: %s", exc)

        if self.channel_pool:
            await self.channel_pool.close()
        if self.connection_pool:
            await self.connection_pool.close()
        
    # ── Message handler ───────────────────────────────────────────────────────

    async def _on_message(self, message: IncomingMessage):
        if not self.running:
            await message.reject(requeue=True)
            return

        async with message.process(ignore_processed=True):

            # 1. Parse
            try:
                body: Dict[str, Any] = json.loads(message.body.decode())
            except Exception as exc:
                logger.error("IndexerConsumer: invalid JSON, discarding: %s", exc)
                await message.reject(requeue=False)
                return

            document_id = body.get("document_id")
            tenant_id   = body.get("tenant_id")
            filename    = body.get("filename")
            chunks_raw  = body.get("chunks", [])
            retry       = body.get("retry_count", 0)

            if not all([document_id, tenant_id, filename]):
                logger.error("IndexerConsumer: missing required fields: %s", body)
                await message.reject(requeue=False)
                return

            logger.info(
                "IndexerConsumer: processing doc=%s (%d chunks, retry=%d/%d)",
                document_id, len(chunks_raw), retry, settings.MAX_RETRY,
            )

            # 2. Update PostgreSQL → indexing
            await self._update_status(document_id, "indexing")

            # 3. Deserialise chunks
            try:
                chunks = [NlpChunk(**c) for c in chunks_raw]
            except Exception as exc:
                logger.error("IndexerConsumer: chunk deserialisation failed: %s", exc)
                await self._update_status(document_id, "index_failed", error=str(exc))
                await message.reject(requeue=False)
                return

            # 4. Embed + store in pgvector (blocking — run in thread pool)
            try:
                doc_uuid, db_tenant_id = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None,
                        self._embed_and_store,
                        document_id,
                        filename,
                        chunks,
                    ),
                    timeout=settings.INDEXER_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error("IndexerConsumer: timeout for doc=%s", document_id)
                await self._update_status(document_id, "index_failed", error="timeout")
                await self._retry_or_dlq(message, body)
                return
            except Exception as exc:
                logger.exception("IndexerConsumer: error for doc=%s: %s", document_id, exc)
                await self._update_status(document_id, "index_failed", error=str(exc))
                await self._retry_or_dlq(message, body)
                return

            # 5. Trigger compliance if valid
            if doc_uuid and db_tenant_id:
                try:
                    await asyncio.to_thread(trigger_compliance_task, str(doc_uuid), str(db_tenant_id))
                except Exception as e:
                    logger.error("[indexer] Failed to trigger compliance task: %s", e)

            # 6. Update PostgreSQL → indexed (pipeline complete ✅)
            await self._update_status(document_id, "indexed")
            logger.info("IndexerConsumer: doc=%s fully indexed. Pipeline complete ✅", document_id)

    # ── Core indexing logic (sync — runs in executor) ─────────────────────────

    def _embed_and_store(
        self,
        document_id: str,
        filename: str,
        chunks: list[NlpChunk],
    ) -> tuple[str | None, str | None]:
        """Embed chunks and upsert into pgvector. Runs synchronously in a thread."""
        texts     = [c.text_en for c in chunks]
        chunk_ids = [c.chunk_id for c in chunks]

        embeddings = self.embedder.embed(texts, chunk_ids)

        with VectorStore(dsn=settings.DB_DSN) as store:
            n, doc_uuid, tenant_id = store.upsert_chunks(chunks, embeddings, doc_id=filename)
            logger.info(
                "IndexerConsumer: upserted %d chunks for doc=%s", n, document_id
            )
            return doc_uuid, tenant_id

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _update_status(
        self,
        document_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        async with self.db_pool.acquire() as conn:
            import uuid
            doc_uuid = uuid.UUID(document_id)
            if error:
                await conn.execute(
                    """
                    UPDATE documents
                    SET status = $1, metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object('error', $2::text), updated_at = now()
                    WHERE id = $3
                    """,
                    status, error, doc_uuid,
                )
            else:
                await conn.execute(
                    """
                    UPDATE documents
                    SET status = $1, updated_at = now()
                    WHERE id = $2
                    """,
                    status, doc_uuid,
                )

    async def _retry_or_dlq(
        self, message: IncomingMessage, body: Dict[str, Any]
    ) -> None:
        retry = body.get("retry_count", 0)
        if retry < settings.MAX_RETRY:
            body["retry_count"] = retry + 1
            async with self.channel_pool.acquire() as channel:
                await channel.default_exchange.publish(
                    Message(
                        json.dumps(body).encode(),
                        content_type="application/json",
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    ),
                    routing_key=settings.INDEXER_QUEUE,
                )
            await message.ack()
            logger.info("IndexerConsumer: republished for retry %d.", retry + 1)
        else:
            logger.error("IndexerConsumer: max retries reached → DLQ.")
            await message.reject(requeue=False)

import asyncio
import asyncpg
    
async def main():
    import os
    import logging
    from dotenv import load_dotenv
    load_dotenv()
    
    logging.basicConfig(level=logging.INFO)
    print("Starting Indexer RabbitMQ Consumer...")

    dsn = os.getenv("DATABASE_URL", "postgresql://postgres:123456789@localhost:5432/postgres")
    if dsn and dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgres://", 1)
        
    db_pool = await asyncpg.create_pool(dsn)

    consumer = IndexerConsumer(db_pool)
    await consumer.start()
    
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        await db_pool.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted by user")

