"""
OCR Consumer Service
Listens to RabbitMQ queue and processes OCR jobs for uploaded documents
"""
import pika
import json
import os
import sys
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from sqlalchemy.orm import Session
from app.database import get_db_session
from app.models import Document
import uuid


def process_ocr_job(message_data: dict):
    """
    Process OCR job for a document
    
    Args:
        message_data: Dictionary containing doc_id, url, and source
    """
    doc_id = message_data.get('doc_id')
    file_url = message_data.get('url')
    source = message_data.get('source')
    
    print(f"\n[OCR] Processing document: {doc_id}")
    print(f"      URL: {file_url}")
    print(f"      Source: {source}")
    
    # Get database session
    db = next(get_db_session())
    
    try:
        # Find the document in database
        document = db.query(Document).filter(Document.id == uuid.UUID(doc_id)).first()
        
        if not document:
            print(f"[ERROR] Document {doc_id} not found in database")
            return False
        
        # Update status to processing
        document.status = "processing"
        document.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        # TODO: Implement actual OCR processing here
        # This is where you would:
        # 1. Download the file from MinIO using file_url
        # 2. Run OCR engine (Tesseract, AWS Textract, etc.)
        # 3. Extract text and metadata
        # 4. Store results
        
        # For now, simulate processing
        print(f"[OCR] Simulating OCR processing for {document.filename}...")
        import time
        time.sleep(2)  # Simulate work
        
        # Update document with results
        ocr_result = {
            "text_extracted": "Sample OCR text content",
            "page_count": 1,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "language_detected": document.language or "en"
        }
        
        document.doc_metadata = ocr_result
        document.status = "completed"
        document.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        print(f"[OCR] ✓ Successfully processed document {doc_id}")
        return True
        
    except Exception as e:
        print(f"[ERROR] OCR processing failed for {doc_id}: {str(e)}")
        
        # Update status to failed
        try:
            document.status = "failed"
            document.doc_metadata = {
                "error": str(e),
                "failed_at": datetime.now(timezone.utc).isoformat()
            }
            db.commit()
        except:
            pass
        
        return False
    
    finally:
        db.close()


def callback(ch, method, properties, body):
    """
    RabbitMQ callback function for processing messages
    """
    try:
        # Parse message
        message = json.loads(body)
        
        # Process the OCR job
        success = process_ocr_job(message)
        
        if success:
            # Acknowledge the message (remove from queue)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        else:
            # Negative acknowledge - requeue the message
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON in message: {e}")
        # Don't requeue malformed messages
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
    except Exception as e:
        print(f"[ERROR] Unexpected error processing message: {e}")
        # Requeue for retry
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def start_consumer():
    """
    Start the RabbitMQ consumer service
    """
    # RabbitMQ connection parameters
    rabbitmq_host = os.getenv('RABBITMQ_HOST', 'localhost')
    rabbitmq_user = os.getenv('RABBITMQ_USER', 'admin')
    rabbitmq_pass = os.getenv('RABBITMQ_PASS', 'secretpassword')
    
    try:
        # Create connection
        credentials = pika.PlainCredentials(rabbitmq_user, rabbitmq_pass)
        parameters = pika.ConnectionParameters(
            host=rabbitmq_host,
            credentials=credentials,
            heartbeat=600,
            blocked_connection_timeout=300
        )
        
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        
        # Declare the queue (ensure it exists)
        channel.queue_declare(queue='ocr_queue', durable=True)
        
        # Set prefetch count for fair dispatch
        channel.basic_qos(prefetch_count=1)
        
        # Set up consumer
        channel.basic_consume(
            queue='ocr_queue',
            on_message_callback=callback
        )
        
        print("=" * 60)
        print("OCR Consumer Service Started")
        print("=" * 60)
        print(f"Connected to RabbitMQ at {rabbitmq_host}")
        print("Waiting for OCR jobs. Press CTRL+C to exit")
        print("=" * 60)
        
        # Start consuming
        channel.start_consuming()
        
    except KeyboardInterrupt:
        print("\n\nShutting down consumer...")
        connection.close()
        print("Consumer stopped.")
        
    except pika.exceptions.AMQPConnectionError as e:
        print(f"[ERROR] Failed to connect to RabbitMQ: {e}")
        print("Please ensure RabbitMQ is running and credentials are correct")
        
    except Exception as e:
        print(f"[ERROR] Consumer error: {e}")
        raise


if __name__ == "__main__":
    start_consumer()
