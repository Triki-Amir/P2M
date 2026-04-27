"""
ocr_service/publisher.py
========================
OCR Service — Publisher.
Called after OCR succeeds.
Publishes OCR results to the NLP queue.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import aio_pika
from aio_pika import Message, DeliveryMode, ExchangeType

import ocr_service.config as settings

logger = logging.getLogger(__name__)


class OCRPublisher:
    """Publishes 'document_ocr_completed' events to the NLP queue."""

    def __init__(self):
        self._connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.Channel] = None
        self._exchange = None

    # ── Connection ────────────────────────────────────────────────────────────

    async def connect(self):
        if self._connection and not self._connection.is_closed:
            return

        logger.info("OCRPublisher: connecting to RabbitMQ...")
        self._connection = await aio_pika.connect_robust(
            settings.RABBITMQ_URL, reconnect_interval=5, timeout=30
        )
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)

        self._exchange = await self._channel.declare_exchange(
            settings.EVENT_EXCHANGE, ExchangeType.DIRECT, durable=True
        )

        # Declare NLP queue with DLX
        dlx_name = f"{settings.NLP_QUEUE}.dlx"
        dlx = await self._channel.declare_exchange(
            dlx_name, ExchangeType.DIRECT, durable=True
        )
        dlq = await self._channel.declare_queue(
            f"{settings.NLP_QUEUE}.dlq", durable=True
        )
        await dlq.bind(dlx, routing_key=settings.NLP_QUEUE)

        await self._channel.declare_queue(
            settings.NLP_QUEUE,
            durable=True,
            arguments={
                "x-message-ttl": 3_600_000,
                "x-max-length": 10_000,
                "x-dead-letter-exchange": dlx_name,
                "x-dead-letter-routing-key": settings.NLP_QUEUE,
            },
        )
        logger.info("OCRPublisher: connected and NLP queue declared.")

    # ── Publish ───────────────────────────────────────────────────────────────

    async def publish_ocr_completed(
        self,
        document_id: str,
        tenant_id: str,
        filename: str,
        pages: List[Dict[str, Any]],
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        """
        Publish OCR completed event to NLP queue.

        Payload forwarded to NLP consumer:
        {
            "document_id":  str,
            "tenant_id":    str,
            "filename":     str,
            "pages":        list[dict]  — serialised OcrPage objects,
            "metadata":     dict,
            "retry_count":  int
        }
        """
        payload = {
            "document_id": document_id,
            "tenant_id":   tenant_id,
            "filename":    filename,
            "pages":       pages,
            "metadata":    metadata or {},
            "retry_count": 0,
        }

        try:
            await self._channel.default_exchange.publish(
                Message(
                    body=json.dumps(payload).encode("utf-8"),
                    content_type="application/json",
                    delivery_mode=DeliveryMode.PERSISTENT,
                ),
                routing_key=settings.NLP_QUEUE,
            )
            logger.info(
                "OCRPublisher: doc=%s → published to '%s'.",
                document_id, settings.NLP_QUEUE,
            )
        except Exception as exc:
            logger.error("OCRPublisher: publish failed: %s", exc, exc_info=True)
            raise

    # ── Cleanup ───────────────────────────────────────────────────────────────

    async def close(self):
        try:
            if self._channel and not self._channel.is_closed:
                await self._channel.close()
            if self._connection and not self._connection.is_closed:
                await self._connection.close()
            logger.info("OCRPublisher: connection closed.")
        except Exception:
            pass
