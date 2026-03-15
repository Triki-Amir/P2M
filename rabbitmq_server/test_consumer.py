"""
Test script for RabbitMQ Consumer
Run this to consume and process messages from the queue
"""
import pika
import json
import time

def callback(ch, method, properties, body):
    """Process messages from the queue"""
    message = json.loads(body)
    print(f"\n[✓] Received message:")
    print(f"    Doc ID: {message.get('doc_id')}")
    print(f"    URL: {message.get('url')}")
    print(f"    Source: {message.get('source')}")
    
    # Simulate processing
    print(f"    Processing document {message.get('doc_id')}...")
    time.sleep(2)  # Simulate work
    print(f"    ✓ Completed processing {message.get('doc_id')}")
    
    # Acknowledge the message
    ch.basic_ack(delivery_tag=method.delivery_tag)

def start_consumer():
    """Start consuming messages from the queue"""
    try:
        # Connect to RabbitMQ
        connection = pika.BlockingConnection(
            pika.ConnectionParameters('localhost')
        )
        channel = connection.channel()
        
        # Declare the queue (in case it doesn't exist)
        channel.queue_declare(queue='ocr_queue', durable=True)
        
        # Set up fair dispatch
        channel.basic_qos(prefetch_count=1)
        
        # Set up the consumer
        channel.basic_consume(
            queue='ocr_queue',
            on_message_callback=callback
        )
        
        print("=" * 50)
        print("RabbitMQ Consumer Started")
        print("=" * 50)
        print("Waiting for messages. Press CTRL+C to exit")
        print("=" * 50)
        
        # Start consuming
        channel.start_consuming()
        
    except KeyboardInterrupt:
        print("\n\nStopping consumer...")
        connection.close()
        print("Consumer stopped.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    start_consumer()
