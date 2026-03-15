"""
Startup script for OCR Consumer Service.
Run this to start processing OCR jobs from the queue.

Usage (from the project root):
    python -m rabbitmq_server.start_consumer
"""
import sys
import os

# Add project root to path so that 'app' and 'rabbitmq_server' packages are importable.
project_root = os.path.join(os.path.dirname(__file__), '..')
if project_root not in sys.path:
    sys.path.insert(0, os.path.abspath(project_root))

from rabbitmq_server.consumers.ocr_services import start_consumer

if __name__ == "__main__":
    print("Starting OCR Consumer Service...")
    print("Make sure RabbitMQ, MinIO, and PostgreSQL are running!")
    print()
    start_consumer()
