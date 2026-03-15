"""
Test script for RabbitMQ Producer
Run this to send test messages to the queue
"""
import sys
sys.path.append('../')

from Producers.ingestion import trigger_ingestion
from Producers.scheduler import trigger_scheduled_check

if __name__ == "__main__":
    print("=" * 50)
    print("Testing RabbitMQ Producer")
    print("=" * 50)
    
    # Test 1: Send ingestion message
    print("\n[Test 1] Sending ingestion message...")
    try:
        trigger_ingestion(doc_id="test_doc_001", file_url="http://example.com/test.pdf")
        print("✓ Ingestion message sent successfully")
    except Exception as e:
        print(f"✗ Failed to send ingestion message: {e}")
    
    # Test 2: Send scheduler message
    print("\n[Test 2] Sending scheduler message...")
    try:
        trigger_scheduled_check()
        print("✓ Scheduler message sent successfully")
    except Exception as e:
        print(f"✗ Failed to send scheduler message: {e}")
    
    print("\n" + "=" * 50)
    print("Check RabbitMQ Management UI at http://localhost:15672")
    print("Go to Queues tab -> ocr_queue -> Get Messages")
    print("=" * 50)
