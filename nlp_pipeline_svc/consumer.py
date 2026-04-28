"""
nlp_pipeline_svc/consumer.py
=============================
NLP Service — Consumer.
Receives document_ocr_completed events from the NLP queue.
Runs NLP pipeline → updates PostgreSQL status → publishes to Indexer queue.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import aio_pika
from aio_pika import Message, IncomingMessage, connect_robust
from aio_pika.pool import Pool

import nlp_pipeline_svc.app.config as settings
from nlp_pipeline_svc.publisher import NLPPublisher
from nlp_pipeline_svc.app.pipeline import NlpOrcestrator
from nlp_pipeline_svc.app import config as nlp_config
from shared import event_bus
from shared.models import OcrDocument
logger = logging.getLogger(__name__)


class NLPConsumer:
    """
    Async RabbitMQ consumer for NLP tasks.

    Flow per message:
        1. Parse payload (document_id, pages, …)
        2. Update PostgreSQL status → 'nlp_processing'
        3. Run NLP pipeline (cleaning, chunking, language detection)
        4. Update PostgreSQL status → 'nlp_done' / 'nlp_failed'
        5. Publish chunks to Indexer queue
    """

    def __init__(self, db_pool):
        """
        Args:
            db_pool: asyncpg connection pool
        """
        self.db_pool = db_pool
        self.publisher = NLPPublisher()

        self.connection_pool: Optional[Pool] = None
        self.channel_pool: Optional[Pool] = None
        self.consumer_tag: Optional[str] = None
        self.running = False

    # ── Connection pools ──────────────────────────────────────────────────────

    async def _create_connection(self) -> aio_pika.RobustConnection:
        return await connect_robust(
            settings.RABBITMQ_URL, timeout=30, reconnect_interval=5, heartbeat=3600
        )

    async def _create_channel(self) -> aio_pika.Channel:
        async with self.connection_pool.acquire() as conn:
            channel = await conn.channel()
            await channel.set_qos(prefetch_count=settings.MAX_WORKERS)
            return channel

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        logger.info("NLPConsumer: connecting to RabbitMQ at %s", settings.RABBITMQ_URL)
        self.running = True

        self.connection_pool = Pool(self._create_connection, max_size=5)
        self.channel_pool = Pool(self._create_channel, max_size=20)

        await self.publisher.connect()

        async with self.channel_pool.acquire() as channel:
            # DLX / DLQ
            dlx = await channel.declare_exchange(
                f"{settings.NLP_QUEUE}.dlx",
                aio_pika.ExchangeType.DIRECT,
                durable=True,
            )
            dlq = await channel.declare_queue(
                f"{settings.NLP_QUEUE}.dlq", durable=True
            )
            await dlq.bind(dlx, routing_key=settings.NLP_QUEUE)

            # Main queue
            queue = await channel.declare_queue(
                settings.NLP_QUEUE,
                durable=True,
                arguments={
                    "x-message-ttl": 3_600_000,
                    "x-max-length": 10_000,
                    "x-dead-letter-exchange": f"{settings.NLP_QUEUE}.dlx",
                    "x-dead-letter-routing-key": settings.NLP_QUEUE,
                },
            )

            self.consumer_tag = await queue.consume(self._on_message, no_ack=False)
            logger.info("NLPConsumer: listening on '%s'", settings.NLP_QUEUE)

    async def stop(self):
        logger.info("NLPConsumer: shutting down...")
        self.running = False
        try:
            if self.consumer_tag:
                async with self.channel_pool.acquire() as channel:
                    await channel.cancel(self.consumer_tag)
        except Exception as exc:
            logger.warning("NLPConsumer: error cancelling tag: %s", exc)

        await self.publisher.close()
        if self.channel_pool:
            await self.channel_pool.close()
        if self.connection_pool:
            await self.connection_pool.close()
        logger.info("NLPConsumer: stopped cleanly.")

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
                logger.error("NLPConsumer: invalid JSON, discarding: %s", exc)
                await message.reject(requeue=False)
                return

            document_id = body.get("document_id")
            tenant_id   = body.get("tenant_id")
            filename    = body.get("filename")
            pages       = body.get("pages", [])
            retry       = body.get("retry_count", 0)
            metadata    = body.get("metadata", {})

            if not all([document_id, tenant_id, filename]):
                logger.error("NLPConsumer: missing required fields: %s", body)
                await message.reject(requeue=False)
                return

            logger.info(
                "NLPConsumer: processing doc=%s (retry=%d/%d)",
                document_id, retry, settings.MAX_RETRY,
            )

            # 2. Update PostgreSQL → nlp_processing
            await self._update_status(document_id, "nlp_processing")

            # 3. Run NLP pipeline
            try:
                def _run_nlp():
                    orchestrator = NlpOrcestrator(
                        max_chunk_chars=nlp_config.MAX_CHUNK_CHARS,
                        fallback_overlap=nlp_config.CHUNK_OVERLAP,
                    )
                    # Convert pages list from message back to OcrPage models
                    from shared.models import OcrPage, OcrDocument
                    page_models = [OcrPage(**p) for p in (pages or [])]
                    ocr_doc = OcrDocument(
                        doc_id=document_id,
                        source_lang=None,
                        pages=page_models
                    )
                    nlp_doc = orchestrator.process_document(ocr_doc)
                    
                    # Instead of saving to disk, just return chunks (microservice decoupling)
                    return [c.dict() for c in nlp_doc.chunks]

                chunks = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, _run_nlp),
                    timeout=settings.NLP_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error("NLPConsumer: timeout for doc=%s", document_id)
                await self._update_status(document_id, "nlp_failed", error="timeout")
                await self._retry_or_dlq(message, body)
                return
            except Exception as exc:
                logger.exception("NLPConsumer: error for doc=%s: %s", document_id, exc)
                await self._update_status(document_id, "nlp_failed", error=str(exc))
                await self._retry_or_dlq(message, body)
                return

            # 4. Update PostgreSQL → nlp_done
            await self._update_status(document_id, "nlp_done")

            # 5. Publish chunks to Indexer queue
            await self.publisher.publish_nlp_completed(
                document_id=document_id,
                tenant_id=tenant_id,
                filename=filename,
                chunks=chunks,         # list[NlpChunk] serialised to dicts
                metadata=metadata,
            )
            logger.info("NLPConsumer: doc=%s → published to Indexer queue.", document_id)

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
                    routing_key=settings.NLP_QUEUE,
                )
            await message.ack()
            logger.info("NLPConsumer: republished for retry %d.", retry + 1)
        else:
            logger.error("NLPConsumer: max retries reached → DLQ.")
            await message.reject(requeue=False)

import asyncio
import asyncpg
    
async def main():
    import os
    import logging
    from dotenv import load_dotenv
    load_dotenv()
    
    logging.basicConfig(level=logging.INFO)
    print("Starting NLP RabbitMQ Consumer...")

    dsn = os.getenv("DATABASE_URL", "postgresql://postgres:123456789@localhost:5432/postgres")
    if dsn and dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgres://", 1)
        
    db_pool = await asyncpg.create_pool(dsn)

    consumer = NLPConsumer(db_pool)
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

