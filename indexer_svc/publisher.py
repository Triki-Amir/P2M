import os
import json
import logging
import pika
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "admin")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "secretpassword")
COMPLIANCE_QUEUE = "compliance_queue"

def get_rabbitmq_connection():
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials)
    return pika.BlockingConnection(parameters)

def trigger_compliance_task(document_id: str, tenant_id: str):
    """
    Publish an event to the compliance queue to trigger the LLM extraction.
    """
    message = {
        "document_id": document_id,
        "tenant_id": tenant_id
    }
    
    try:
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        channel.queue_declare(queue=COMPLIANCE_QUEUE, durable=True)
        
        channel.basic_publish(
            exchange="",
            routing_key=COMPLIANCE_QUEUE,
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,
            ))
        
        logger.info(f"Published compliance task for doc {document_id}")
        connection.close()
    except Exception as e:
        logger.error(f"Failed to publish compliance task: {e}")
