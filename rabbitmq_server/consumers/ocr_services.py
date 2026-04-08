"""
OCR Consumer Service
Listens to RabbitMQ queue and processes OCR jobs for uploaded documents
"""
import pika
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote

# Add parent directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from minio import Minio
from app.database import get_db_session
from app.models import Document
from ocr_service.main import run as run_ocr
from nlp_pipeline_svc.app.main import run_consumer as run_nlp
from indexer_svc.app.main import run_indexer
import uuid


def _parse_bucket_and_object(file_url: str) -> tuple[str, str]:
    parsed = urlparse(file_url)
    path_parts = parsed.path.lstrip('/').split('/', 1)
    if len(path_parts) != 2 or not all(path_parts):
        raise ValueError(f"Invalid MinIO URL path: {file_url}")
    return path_parts[0], unquote(path_parts[1])


def _build_minio_client(file_url: str) -> Minio:
    parsed = urlparse(file_url)
    endpoint = parsed.netloc or os.getenv('MINIO_ENDPOINT', 'localhost:9000')
    secure = parsed.scheme == 'https'
    return Minio(
        endpoint,
        access_key=os.getenv('MINIO_ACCESS_KEY', 'admin'),
        secret_key=os.getenv('MINIO_SECRET_KEY', 'password123'),
        secure=secure,
    )


def _download_pdf_from_minio(file_url: str, destination: Path) -> Path:
    bucket, object_name = _parse_bucket_and_object(file_url)
    client = _build_minio_client(file_url)
    destination.parent.mkdir(parents=True, exist_ok=True)
    client.fget_object(bucket, object_name, str(destination))
    return destination


def process_ocr_job(message_data: dict):
    """
    Process OCR job for a document
    
    Args:
        message_data: Dictionary containing doc_id, url, and source
    """
    doc_id = message_data.get('doc_id')
    file_url = message_data.get('url')
    source = message_data.get('source')

    if not doc_id or not file_url:
        print(f"[ERROR] Missing required fields in message: {message_data}")
        return False
    
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

        # Real processing path: download PDF from MinIO and run OCR -> NLP -> Indexer
        with TemporaryDirectory(prefix="p2m_") as tmp_dir:
            local_pdf = Path(tmp_dir) / Path(document.filename or f"{doc_id}.pdf").name
            print(f"[OCR] Downloading from MinIO to {local_pdf}...")
            _download_pdf_from_minio(file_url, local_pdf)

            print(f"[OCR] Running OCR for {document.filename}...")
            run_ocr(local_pdf)

            document.status = "ocr_completed"
            document.updated_at = datetime.now(timezone.utc)
            db.commit()

            print("[NLP] Running NLP pipeline...")
            nlp_doc = run_nlp()
            if nlp_doc is None:
                raise RuntimeError("NLP pipeline failed or produced no output")

            document.status = "nlp_completed"
            document.updated_at = datetime.now(timezone.utc)
            db.commit()

            print("[INDEXER] Running indexer...")
            indexed_count = run_indexer()

        document.doc_metadata = {
            **(document.doc_metadata or {}),
            "pipeline": {
                "source": source,
                "file_url": file_url,
                "indexed_chunks": indexed_count,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        }
        document.status = "completed"
        document.updated_at = datetime.now(timezone.utc)
        db.commit()
        
        print(f"[OCR] ✓ Successfully processed document {doc_id}")
        return True
        
    except Exception as e:
        print(f"[ERROR] OCR processing failed for {doc_id}: {str(e)}")
        
        # Update status to failed
        try:
            if 'document' in locals() and document is not None:
                document.status = "failed"
                document.doc_metadata = {
                    **(document.doc_metadata or {}),
                    "error": str(e),
                    "failed_at": datetime.now(timezone.utc).isoformat()
                }
                db.commit()
        except Exception:
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
