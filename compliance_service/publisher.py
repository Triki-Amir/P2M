import os
import json
import logging
import pika

logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "guest")
COMPLIANCE_UI_EXCHANGE = "ui_events_exchange"

def get_rabbitmq_connection():
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials)
    return pika.BlockingConnection(parameters)

def publish_compliance_result(document_id: str, tenant_id: str, is_compliant: bool, metadata: dict):
    """
    Publish an event back to the system (or frontend WebSockets) indicating
    the Appel d'Offre compliance status.
    """
    message = {
        "event_type": "compliance_completed",
        "document_id": document_id,
        "tenant_id": tenant_id,
        "is_compliant": is_compliant,
        "metadata": metadata
    }
    
    try:
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        channel.exchange_declare(exchange=COMPLIANCE_UI_EXCHANGE, exchange_type='fanout')
        
        channel.basic_publish(
            exchange=COMPLIANCE_UI_EXCHANGE,
            routing_key='', # Fanout to all queues bound to UI elements
            body=json.dumps(message),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            ))
        
        logger.info(f"Published compliance result for doc {document_id}")
        connection.close()
    except Exception as e:
        logger.error(f"Failed to publish compliance result: {e}")
