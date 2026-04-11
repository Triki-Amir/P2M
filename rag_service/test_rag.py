import asyncio
import websockets
import json

async def test():
    uri = "ws://localhost:8001/rag/ws"
    async with websockets.connect(uri) as ws:

        # Wait for READY
        msg = await ws.recv()
        print("Server:", msg)

        # Send query
        await ws.send(json.dumps({
            "document_id": "3054c122-31d4-4024-bedd-ba5fc26c5365",
            "query": "Where and when are the offers opened?",
            "conversation_history": []
        }))

        # Stream responses
        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            if data["type"] == "retrieving":
                print("\n🔍 Retrieving chunks...")
            elif data["type"] == "sources":
                print(f"📄 Got {len(data['data'])} source chunks")
                for i, chunk in enumerate(data["data"], 1):
                    print(f"  [{i}] score={chunk['score']} | {chunk['content'][:80]}...")
            elif data["type"] == "generating":
                print("\n🤖 Generating answer...\n")
            elif data["type"] == "token":
                print(data["data"]["text"], end="", flush=True)
            elif data["type"] == "done":
                print(f"\n\n✅ Done! total_tokens={data['data']['total_tokens']}")
                break
            elif data["type"] == "error":
                print(f"\n❌ Error: {data['data']['message']} (code: {data['data']['code']})")
                break

asyncio.run(test())