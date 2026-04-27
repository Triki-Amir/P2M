import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect("postgresql://postgres:123456789@localhost:5432/postgres")
    val = await conn.fetchval("SELECT COUNT(*) FROM chunks WHERE document_id = $1", "c33cfc00-93e4-422c-9b1c-16e0bf7ae896")
    print(f"Chunks for doc: {val}")
    await conn.close()

asyncio.run(main())

