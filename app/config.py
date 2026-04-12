"""
app/config.py
=============
Configuration for the Ingestion (upload) service.
"""
import os

# ── MinIO ─────────────────────────────────────────────────────────────────────
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "pdf-storage")

# ── RabbitMQ ──────────────────────────────────────────────────────────────────
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://admin:secretpassword@localhost/")
EVENT_EXCHANGE = os.getenv("EVENT_EXCHANGE", "p2m_events")
OCR_QUEUE      = os.getenv("OCR_QUEUE",      "ocr_queue")
MAX_RETRY      = int(os.getenv("MAX_RETRY",  "3"))