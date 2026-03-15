import pika
import json
import os

def trigger_ingestion(doc_id, file_url):
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
    channel.queue_declare(queue='ocr_queue', durable=True)

    message = {"doc_id": doc_id, "url": file_url, "source": "user_upload"}
    
    channel.basic_publish(
        exchange='',
        routing_key='ocr_queue',
        body=json.dumps(message),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    print(f" [➡] Ingestion: Document {doc_id} sent to OCR.")
    connection.close()