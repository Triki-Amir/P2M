import asyncio
import websockets
import json

async def test():
    async with websockets.connect("ws://localhost:8001/rag/ws") as ws:
        msg = await ws.recv()
        print("Rcv:", msg)
        await ws.send(json.dumps({"document_id": "c33cfc00-93e4-422c-9b1c-16e0bf7ae896","query": "hello"}))
        while True:
            try:
                resp = await ws.recv()
                print("Rcv:", resp)
                data = json.loads(resp)
                if data["type"] == "done" or data["type"] == "error":
                    break
            except Exception as e:
                print("Error:", e)
                break

asyncio.run(test())
