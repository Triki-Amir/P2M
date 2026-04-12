"""
nlp_pipeline_svc/publisher.py
==============================
NLP Service — Publisher.
Called after NLP succeeds.
Publishes NLP chunks to the Indexer queue.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import aio_pika
from aio_pika import Message, DeliveryMode, ExchangeType

import nlp_pipeline_svc.app.config as settings

logger = logging.getLogger(__name__)


class NLPPublisher:
    """Publishes 'document_nlp_completed' events to the Indexer queue."""

    def __init__(self):
        self._connection: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.Channel] = None
        self._exchange = None

    # ── Connection ────────────────────────────────────────────────────────────

    async def connect(self):
        if self._connection and not self._connection.is_closed:
            return

        logger.info("NLPPublisher: connecting to RabbitMQ...")
        self._connection = await aio_pika.connect_robust(
            settings.RABBITMQ_URL, reconnect_interval=5, timeout=30
        )
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)

        self._exchange = await self._channel.declare_exchange(
            settings.EVENT_EXCHANGE, ExchangeType.DIRECT, durable=True
        )

        # Declare Indexer queue with DLX
        dlx_name = f"{settings.INDEXER_QUEUE}.dlx"
        dlx = await self._channel.declare_exchange(
            dlx_name, ExchangeType.DIRECT, durable=True
        )
        dlq = await self._channel.declare_queue(
            f"{settings.INDEXER_QUEUE}.dlq", durable=True
        )
        await dlq.bind(dlx, routing_key=settings.INDEXER_QUEUE)

        await self._channel.declare_queue(
            settings.INDEXER_QUEUE,
            durable=True,
            arguments={
                "x-message-ttl": 3_600_000,
                "x-max-length": 10_000,
                "x-dead-letter-exchange": dlx_name,
                "x-dead-letter-routing-key": settings.INDEXER_QUEUE,
            },
        )
        logger.info("NLPPublisher: connected and Indexer queue declared.")

    # ── Publish ───────────────────────────────────────────────────────────────

    async def publish_nlp_completed(
        self,
        document_id: str,
        tenant_id: str,
        filename: str,
        chunks: List[Dict[str, Any]],
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        """
        Publish NLP completed event to Indexer queue.

        Payload forwarded to Indexer consumer:
        {
            "document_id":  str,
            "tenant_id":    str,
            "filename":     str,
            "chunks":       list[dict]  — serialised NlpChunk objects,
            "metadata":     dict,
            "retry_count":  int
        }
        """
        payload = {
            "document_id": document_id,
            "tenant_id":   tenant_id,
            "filename":    filename,
            "chunks":      chunks,
            "metadata":    metadata or {},
            "retry_count": 0,
        }

        try:
            await self._exchange.publish(
                Message(
                    body=json.dumps(payload).encode("utf-8"),
                    content_type="application/json",
                    delivery_mode=DeliveryMode.PERSISTENT,
                ),
                routing_key=settings.INDEXER_QUEUE,
            )
            logger.info(
                "NLPPublisher: doc=%s → published to '%s'.",
                document_id, settings.INDEXER_QUEUE,
            )
        except Exception as exc:
            logger.error("NLPPublisher: publish failed: %s", exc, exc_info=True)
            raise

    # ── Cleanup ───────────────────────────────────────────────────────────────

    async def close(self):
        try:
            if self._channel and not self._channel.is_closed:
                await self._channel.close()
            if self._connection and not self._connection.is_closed:
                await self._connection.close()
            logger.info("NLPPublisher: connection closed.")
        except Exception:
            pass
