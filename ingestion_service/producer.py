import pika
import json
import os
from dotenv import load_dotenv

load_dotenv()

def trigger_ingestion(doc_id, file_url, tenant_id=None, storage_path=None, filename=None):
    # RabbitMQ connection with authentication
    credentials = pika.PlainCredentials(
        os.getenv('RABBITMQ_USER', 'admin'),
        os.getenv('RABBITMQ_PASS', 'secretpassword')
    )
    parameters = pika.ConnectionParameters(
        host=os.getenv('RABBITMQ_HOST', 'localhost'),
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300
    )
    
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    
    # Must match the exact arguments used in the async consumer
    channel.queue_declare(
        queue='ocr_queue', 
        durable=True,
        arguments={
            "x-message-ttl": 3600000,
            "x-max-length": 10000,
            "x-dead-letter-exchange": "ocr_queue.dlx",
            "x-dead-letter-routing-key": "ocr_queue",
        }
    )

    message = {
        "document_id": doc_id, 
        "url": file_url, 
        "source": "user_upload", 
        "tenant_id": tenant_id,
        "storage_path": storage_path,
        "filename": filename
    }
    
    channel.basic_publish(
        exchange='',
        routing_key='ocr_queue',
        body=json.dumps(message),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    print(f" [➡] Ingestion: Document {doc_id} sent to OCR.")
    connection.close()