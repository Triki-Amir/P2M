import json
import logging
import os
import pika

from app.extractor import run_compliance_for_document

logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST")
RABBITMQ_USER = os.getenv("RABBITMQ_USER")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS")
QUEUE_NAME = "compliance_queue"

def get_rabbitmq_connection():
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials)
    return pika.BlockingConnection(parameters)

def process_message(ch, method, properties, body):
    try:
        msg = json.loads(body.decode('utf-8'))
        doc_id = msg.get("document_id")
        tenant_id = msg.get("tenant_id")
        
        logger.info(f"Received compliance task for document {doc_id} and tenant {tenant_id}")
        
        if doc_id and tenant_id:
            run_compliance_for_document(doc_id, tenant_id)
            logger.info(f"Compliance task completed for document {doc_id}.")
        elif doc_id and not tenant_id:
            logger.error("tenant_id missing in the message. Cannot perform compliance comparison without a tenant.")
        else:
            logger.error("Invalid message format: missing document_id. Cannot proceed.")
            
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error(f"Error processing compliance message: {e}")
        # Reject and requeue or send to DLQ based on policy
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def start_consumer():
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_message)
    
    logger.info(f"[*] Waiting for messages in {QUEUE_NAME}. To exit press CTRL+C")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    connection.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_consumer()
