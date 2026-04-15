"""
DEPRECATED MONOLITHIC CONSUMER.
DO NOT USE THIS SCRIPT FOR TRUE MICROSERVICES.
Instead, run each service's individual consumer module:
python -m ocr_service.consumer
python -m nlp_pipeline_svc.consumer
python -m indexer_svc.consumer
python -m compliance_service.consumer
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
