"""
Startup script for OCR Consumer Service
Run this to start processing OCR jobs from the queue
"""
import sys
import os

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from consumers.ocr_services import start_consumer

if __name__ == "__main__":
    print("Starting OCR Consumer Service...")
    print("Make sure RabbitMQ and PostgreSQL are running!")
    print()
    start_consumer()
