
import asyncio, aio_pika
async def main():
    conn = await aio_pika.connect_robust("amqp://admin:secretpassword@localhost/")
    ch = await conn.channel()
    await ch.default_exchange.publish(aio_pika.Message(b"test"), routing_key="nlp_queue")
    print("Published")
    await conn.close()
asyncio.run(main())

