"""
ocr_service/consumer.py
=======================
OCR Service — Consumer.
Receives document_uploaded events from the OCR queue.
Runs OCR → updates PostgreSQL status → publishes to NLP queue.
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import aio_pika
from aio_pika import Message, IncomingMessage, connect_robust
from aio_pika.pool import Pool

import ocr_service.config as settings
from ocr_service.publisher import OCRPublisher
from ocr_service.main import run as _run_ocr
from ocr_service.pdf_to_images import cleanup_images
import tempfile, os
logger = logging.getLogger(__name__)


class OCRConsumer:
    """
    Async RabbitMQ consumer for OCR tasks.

    Flow per message:
        1. Parse payload (document_id, storage_path, …)
        2. Update PostgreSQL status → 'ocr_processing'
        3. Run OCR pipeline
        4. Update PostgreSQL status → 'ocr_done' / 'ocr_failed'
        5. Publish result to NLP queue
    """

    def __init__(self, db_pool, minio_client):
        """
        Args:
            db_pool:      asyncpg connection pool (shared with FastAPI app)
            minio_client: MinIO client to fetch the PDF bytes
        """
        self.db_pool = db_pool
        self.minio_client = minio_client
        self.publisher = OCRPublisher()

        self.connection_pool: Optional[Pool] = None
        self.channel_pool: Optional[Pool] = None
        self.consumer_tag: Optional[str] = None
        self.running = False

    # ── Connection pools ──────────────────────────────────────────────────────

    async def _create_connection(self) -> aio_pika.RobustConnection:
        return await connect_robust(
            settings.RABBITMQ_URL,
            timeout=30,
            reconnect_interval=5,
            heartbeat=3600
        )

    async def _create_channel(self) -> aio_pika.Channel:
        async with self.connection_pool.acquire() as conn:
            channel = await conn.channel()
            await channel.set_qos(prefetch_count=settings.MAX_WORKERS)
            return channel

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        logger.info("OCRConsumer: connecting to RabbitMQ at %s", settings.RABBITMQ_URL)
        self.running = True

        self.connection_pool = Pool(self._create_connection, max_size=5)
        self.channel_pool = Pool(self._create_channel, max_size=20)

        await self.publisher.connect()

        async with self.channel_pool.acquire() as channel:
            # DLX / DLQ
            dlx = await channel.declare_exchange(
                f"{settings.OCR_QUEUE}.dlx",
                aio_pika.ExchangeType.DIRECT,
                durable=True,
            )
            dlq = await channel.declare_queue(
                f"{settings.OCR_QUEUE}.dlq", durable=True
            )
            await dlq.bind(dlx, routing_key=settings.OCR_QUEUE)

            # Main queue
            queue = await channel.declare_queue(
                settings.OCR_QUEUE,
                durable=True,
                arguments={
                    "x-message-ttl": 3_600_000,
                    "x-max-length": 10_000,
                    "x-dead-letter-exchange": f"{settings.OCR_QUEUE}.dlx",
                    "x-dead-letter-routing-key": settings.OCR_QUEUE,
                },
            )

            self.consumer_tag = await queue.consume(self._on_message, no_ack=False)
            logger.info("OCRConsumer: listening on '%s'", settings.OCR_QUEUE)

    async def stop(self):
        logger.info("OCRConsumer: shutting down...")
        self.running = False
        try:
            if self.consumer_tag:
                async with self.channel_pool.acquire() as channel:
                    await channel.cancel(self.consumer_tag)
        except Exception as exc:
            logger.warning("OCRConsumer: error cancelling tag: %s", exc)

        await self.publisher.close()
        if self.channel_pool:
            await self.channel_pool.close()
        if self.connection_pool:
            await self.connection_pool.close()
        logger.info("OCRConsumer: stopped cleanly.")

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
                logger.error("OCRConsumer: invalid JSON, discarding: %s", exc)
                await message.reject(requeue=False)
                return

            document_id  = body.get("document_id")
            tenant_id    = body.get("tenant_id")
            storage_path = body.get("storage_path")
            filename     = body.get("filename")
            retry        = body.get("retry_count", 0)
            metadata     = body.get("metadata", {})

            if not all([document_id, tenant_id, storage_path, filename]):
                logger.error("OCRConsumer: missing required fields: %s", body)
                await message.reject(requeue=False)
                return

            logger.info(
                "OCRConsumer: processing doc=%s (retry=%d/%d)",
                document_id, retry, settings.MAX_RETRY,
            )

            # 2. Update PostgreSQL → ocr_processing
            await self._update_status(document_id, "ocr_processing")

            # 3. Run OCR
            try:
                def _download_and_run():
                    # Download PDF from MinIO to a temp file
                    tmp = tempfile.NamedTemporaryFile(
                        suffix=".pdf", delete=False,
                        prefix=f"{filename}_"
                    )
                    tmp.close()  # Close file handle so MinIO can overwrite it on Windows
                    self.minio_client.fget_object(
                        bucket_name=storage_path.split("/")[0],
                        object_name="/".join(storage_path.split("/")[1:]),
                        file_path=tmp.name,
                    )
                    try:
                        return _run_ocr(tmp.name)
                    finally:
                        os.unlink(tmp.name)

                ocr_result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, _download_and_run),
                    timeout=settings.OCR_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error("OCRConsumer: timeout for doc=%s", document_id)
                await self._update_status(document_id, "ocr_failed", error="timeout")
                await self._retry_or_dlq(message, body)
                return
            except Exception as exc:
                logger.exception("OCRConsumer: error for doc=%s: %s", document_id, exc)
                await self._update_status(document_id, "ocr_failed", error=str(exc))
                await self._retry_or_dlq(message, body)
                return

            # 4. Update PostgreSQL → ocr_done
            await self._update_status(document_id, "ocr_done")

            # 5. Publish to NLP queue
            await self.publisher.publish_ocr_completed(
                document_id=document_id,
                tenant_id=tenant_id,
                filename=filename,
                pages=ocr_result,        # list[OcrPage] serialised to dicts
                metadata=metadata,
            )
            logger.info("OCRConsumer: doc=%s → published to NLP queue.", document_id)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _update_status(
        self,
        document_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        """Update the documents table with the current pipeline status."""
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
        """Republish with incremented retry or send to DLQ if max retries reached."""
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
                    routing_key=settings.OCR_QUEUE,
                )
            await message.ack()
            logger.info("OCRConsumer: republished for retry %d.", retry + 1)
        else:
            logger.error("OCRConsumer: max retries reached → DLQ.")
            await message.reject(requeue=False)

import asyncio
import asyncpg
from minio import Minio

async def main():
    import os
    import logging
    from dotenv import load_dotenv
    load_dotenv()
    
    logging.basicConfig(level=logging.INFO)
    print("Starting OCR RabbitMQ Consumer...")

    dsn = os.getenv("DATABASE_URL", "postgresql://postgres:123456789@localhost:5432/postgres")
    if dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgres://", 1)
        
    db_pool = await asyncpg.create_pool(dsn)

    mc = Minio(
        os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "admin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "password123"),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true"
    )

    consumer = OCRConsumer(db_pool, mc)
    await consumer.start()
    
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        await db_pool.close()

if __name__ == "__main__":
    target = ""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted by user")

