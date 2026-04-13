import pika
import json
import os

def trigger_scheduled_check():
    # RabbitMQ connection with authentication
    credentials = pika.PlainCredentials(
        os.getenv('RABBITMQ_USER'),
        os.getenv('RABBITMQ_PASS')
    )
    parameters = pika.ConnectionParameters(
        host=os.getenv('RABBITMQ_HOST'),
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300
    )
    
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    channel.queue_declare(queue='ocr_queue', durable=True)

    # Example: Re-processing a stuck document
    message = {"doc_id": "sys_check_99", "url": "internal/path", "source": "scheduler"}
    
    channel.basic_publish(exchange='', routing_key='ocr_queue', body=json.dumps(message))
    print(" [➡] Scheduler: System check task injected.")
    connection.close()