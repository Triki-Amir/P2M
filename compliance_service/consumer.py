import json
import logging
import os
import sys
from pathlib import Path
import asyncio
import aio_pika

# Add project root to sys.path so we can import from 'app' and 'compliance_service'
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from compliance_service.app.extractor import run_compliance_for_document

logger = logging.getLogger(__name__)

from dotenv import load_dotenv

load_dotenv()

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "admin")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "secretpassword")
QUEUE_NAME = "compliance_queue"
RABBITMQ_URL = os.getenv("RABBITMQ_URL", f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}/")

async def process_message(message: aio_pika.IncomingMessage):
    async with message.process(requeue=False):
        try:
            body = message.body.decode('utf-8')
            msg = json.loads(body)
            doc_id = msg.get("document_id")
            tenant_id = msg.get("tenant_id")
            
            logger.info(f"Received compliance task for document {doc_id} and tenant {tenant_id}")
            
            if doc_id and tenant_id:
                await run_compliance_for_document(doc_id, tenant_id)
                logger.info(f"Compliance task completed for document {doc_id}.")
            elif doc_id and not tenant_id:
                logger.error("tenant_id missing in the message. Cannot perform compliance comparison without a tenant.")
            else:
                logger.error("Invalid message format: missing document_id. Cannot proceed.")
                
        except Exception as e:
            logger.error(f"Error processing compliance message: {e}")
            raise

async def start_consumer():
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    queue = await channel.declare_queue(QUEUE_NAME, durable=True)
    
    await queue.consume(process_message)
    
    logger.info(f"[*] Waiting for messages in {QUEUE_NAME}. To exit press CTRL+C")
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        await connection.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(start_consumer())
    except KeyboardInterrupt:
        pass
