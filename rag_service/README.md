# P2M RAG Service

Completes the document processing pipeline with a **Hybrid Retrieval-Augmented Generation** layer.

## Architecture

```
Client (React UI)
    │  WebSocket  ws://localhost:8001/rag/ws
    ▼
┌─────────────────────────────────────────────────┐
│              RAG Service (FastAPI)              │
│                                                 │
│  websocket_handler.py  ←  RAGSession            │
│         │                                       │
│         ▼                                       │
│     pipeline.py  ←  RAGPipeline.run()           │
│      ┌──┴──────────────────────┐                │
│      ▼                         ▼                │
│  retriever.py             generator.py          │
│  HybridRetriever          OllamaGenerator       │
│  ┌────────────┐            (llama3 stream)      │
│  │  pgvector  │                                 │
│  │  cosine ──►│──┐                              │
│  │  BM25   ──►│──┤  RRF Fusion                  │
│  └────────────┘  ▼                              │
│            top-k chunks                         │
└─────────────────────────────────────────────────┘
         │                    │
    PostgreSQL            Ollama
    (pgvector)            (local)
```

## File Structure

```
rag_service/
├── __init__.py            # Public exports
├── config.py              # All settings (env-driven)
├── models.py              # Pydantic schemas for WS messages
├── retriever.py           # Hybrid search (pgvector + BM25 → RRF)
├── generator.py           # Ollama llama3 streaming client
├── pipeline.py            # Orchestrator: retrieve → prompt → stream
├── websocket_handler.py   # WebSocket session management
└── start_rag.py           # FastAPI entry point
```

## Setup

### 1. Install dependencies

```bash
pip install fastapi uvicorn[standard] asyncpg httpx pydantic pydantic-settings
```

### 2. Plug in your embedding model

Open `rag_service/start_rag.py` and implement `embed_query()`:

```python
# Example: sentence-transformers
from sentence_transformers import SentenceTransformer
import asyncio

_model = SentenceTransformer("intfloat/multilingual-e5-base")  # same model your Indexer used

async def embed_query(text: str) -> list[float]:
    loop = asyncio.get_event_loop()
    vec = await loop.run_in_executor(None, _model.encode, text)
    return vec.tolist()
```

> ⚠️ The model must be **identical** to what your Indexer used when storing embeddings.

### 3. Configure `.env`

Add to your root `.env`:

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=123456789
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Must match your document_chunks table schema
CHUNKS_TABLE=document_chunks
CHUNK_TEXT_COL=content
CHUNK_EMBEDDING_COL=embedding
EMBEDDING_DIM=768

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
```

### 4. Pull the model in Ollama

```bash
ollama pull llama3
ollama serve          # keep running in background
```

### 5. Start the RAG service

```bash
# From project root, with venv active:
python rag_service/start_rag.py
```

> Runs on `ws://localhost:8001/rag/ws`

## WebSocket Protocol

### Client → Server

```json
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "query": "What are the payment terms?",
  "conversation_history": []
}
```

### Server → Client (event stream)

| `type`        | `data`                              | Description                      |
|---------------|-------------------------------------|----------------------------------|
| `ready`       | `{message}`                         | Connection established           |
| `retrieving`  | `{document_id, query}`              | Retrieval started                |
| `sources`     | `[{chunk_id, content, score, ...}]` | Retrieved chunks (citations)     |
| `generating`  | `{message}`                         | LLM generation started           |
| `token`       | `{text}`                            | Single streamed token            |
| `done`        | `{total_tokens}`                    | Generation complete              |
| `error`       | `{message, code}`                   | Something went wrong             |

## Retrieval Strategy: Hybrid RRF

1. **Semantic search** — pgvector cosine similarity (`<=>`) for top-10 candidates
2. **BM25 keyword search** — PostgreSQL `tsvector` + `ts_rank_cd` for top-10 candidates  
3. **RRF fusion** — `score = Σ 1/(60 + rank)` — deduplication + re-ranking → top-5 sent to LLM

## Health Checks

```
GET http://localhost:8001/health        → liveness
GET http://localhost:8001/health/model  → Ollama model availability
```
