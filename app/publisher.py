"""
app/publisher.py
================
Ingestion Service — Publisher only.
Called after a document is uploaded and stored in MinIO.
Publishes a message to the OCR queue to trigger processing.
"""

import json
import logging
from typing import Any, Dict, Optional

import aio_pika
from aio_pika import Message, DeliveryMode, ExchangeType

import app.config as settings # local config with RabbitMQ settings

logger = logging.getLogger(__name__)


class IngestionPublisher:
    """
    Publishes 'document_uploaded' events to the OCR queue.
    Called once per uploaded document from the FastAPI upload endpoint.
    """

    def __init__(self):
        self._connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.Channel] = None
        self._exchange = None

    # ── Lazy connection ───────────────────────────────────────────────────────

    async def _connect(self):
        """Establish connection and declare exchange + queues if not already open."""
        if self._connection and not self._connection.is_closed:
            return

        logger.info("IngestionPublisher: connecting to RabbitMQ...")

        self._connection = await aio_pika.connect_robust(
            settings.RABBITMQ_URL,
            reconnect_interval=5,
            timeout=30,
        )
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)

        # Declare direct exchange
        self._exchange = await self._channel.declare_exchange(
            settings.EVENT_EXCHANGE,
            ExchangeType.DIRECT,
            durable=True,
        )

        # Declare OCR queue with DLX
        dlx_name = f"{settings.OCR_QUEUE}.dlx"
        dlx = await self._channel.declare_exchange(
            dlx_name, ExchangeType.DIRECT, durable=True
        )
        dlq = await self._channel.declare_queue(
            f"{settings.OCR_QUEUE}.dlq", durable=True
        )
        await dlq.bind(dlx, routing_key=settings.OCR_QUEUE)

        await self._channel.declare_queue(
            settings.OCR_QUEUE,
            durable=True,
            arguments={
                "x-message-ttl": 3_600_000,
                "x-max-length": 10_000,
                "x-dead-letter-exchange": dlx_name,
                "x-dead-letter-routing-key": settings.OCR_QUEUE,
            },
        )

        logger.info("IngestionPublisher: connected and queues declared.")

    # ── Publish ───────────────────────────────────────────────────────────────

    async def publish_document_uploaded(
        self,
        document_id: str,
        tenant_id: str,
        storage_path: str,
        filename: str,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        """
        Publish a document_uploaded event to the OCR queue.

        Payload forwarded to OCR consumer:
        {
            "document_id":  str  — UUID from documents table,
            "tenant_id":    str  — tenant identifier,
            "storage_path": str  — MinIO object path (e.g. "tenants/abc/file.pdf"),
            "filename":     str  — original filename,
            "metadata":     dict — optional extra fields,
            "retry_count":  int  — starts at 0
        }
        """
        await self._connect()

        payload = {
            "document_id":  document_id,
            "tenant_id":    tenant_id,
            "storage_path": storage_path,
            "filename":     filename,
            "metadata":     metadata or {},
            "retry_count":  0,
        }

        try:
            await self._exchange.publish(
                Message(
                    body=json.dumps(payload).encode("utf-8"),
                    content_type="application/json",
                    delivery_mode=DeliveryMode.PERSISTENT,
                ),
                routing_key=settings.OCR_QUEUE,
            )
            logger.info(
                "IngestionPublisher: queued doc=%s → %s",
                document_id, settings.OCR_QUEUE,
            )
        except Exception as exc:
            logger.error("IngestionPublisher: publish failed: %s", exc, exc_info=True)
            raise

    # ── Cleanup ───────────────────────────────────────────────────────────────

    async def close(self):
        try:
            if self._channel and not self._channel.is_closed:
                await self._channel.close()
            if self._connection and not self._connection.is_closed:
                await self._connection.close()
            logger.info("IngestionPublisher: connection closed.")
        except Exception:
            pass


# Singleton — import and use directly in api.py
publisher = IngestionPublisher()
