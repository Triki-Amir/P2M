"""
RAG Service — Entry Point
Starts a standalone FastAPI app exposing the RAG WebSocket endpoint.

Run with:
    python rag_service/start_rag.py

Or via uvicorn directly:
    uvicorn rag_service.start_rag:app --host 0.0.0.0 --port 8001 --reload

WebSocket endpoint:
    ws://localhost:8001/rag/ws

HTTP health endpoints:
    GET /health        → basic liveness check
    GET /health/model  → checks Ollama model availability
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

# ── Adjust import path when run directly ─────────────────────────────────────
if __name__ == "__main__":
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_service.config import get_settings
from rag_service.generator import OllamaGenerator
from rag_service.pipeline import RAGPipeline, build_pipeline
from rag_service.websocket_handler import handle_rag_websocket

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("rag_service.start")

# ── Settings ──────────────────────────────────────────────────────────────────
settings = get_settings()

# ── Embedding function ────────────────────────────────────────────────────────
from FlagEmbedding import BGEM3FlagModel

# Loaded once at startup — expensive, ~1-2GB model
_embedder = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)

async def embed_query(text: str) -> list[float]:
    loop = asyncio.get_event_loop()
    output = await loop.run_in_executor(
        None,
        lambda: _embedder.encode(
            [text],
            return_dense=True,
            return_sparse=False,   # we only need dense for pgvector <#>
            return_colbert_vecs=False,
        )
    )
    return output["dense_vecs"][0].tolist()  # (1024,) numpy → list[float]

# ── Application state (shared across requests) ─────────────────────────────────
_pipeline: RAGPipeline | None = None


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline
    logger.info("Starting RAG service...")
    _pipeline = await build_pipeline(settings=settings, embed_fn=embed_query)
    logger.info(
        "✅ RAG service ready | WS endpoint: ws://%s:%d%s",
        settings.WS_HOST, settings.WS_PORT, settings.WS_PATH,
    )
    yield
    # Teardown
    if _pipeline:
        await _pipeline.retriever.close()
        await _pipeline.generator.close()
    logger.info("RAG service shut down.")


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="P2M RAG Service",
    description="Hybrid Retrieval-Augmented Generation over indexed tender documents.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── HTTP Health Endpoints ─────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "service": "P2M RAG", "version": "1.0.0"}


@app.get("/health/model", tags=["health"])
async def health_model() -> dict:
    """Checks whether the Ollama model is available."""
    gen = OllamaGenerator(settings)
    await gen.connect()
    available = await gen.check_model_available()
    await gen.close()
    return {
        "model": settings.OLLAMA_MODEL,
        "ollama_url": settings.OLLAMA_BASE_URL,
        "available": available,
    }


# ── WebSocket Endpoint ────────────────────────────────────────────────────────

@app.websocket(settings.WS_PATH)
async def rag_websocket(websocket: WebSocket) -> None:
    """
    Main RAG WebSocket endpoint.

    Client protocol:
        1. Connect to ws://localhost:8001/rag/ws
        2. Receive: {"type": "ready", "data": {...}}
        3. Send:    {"document_id": "<uuid>", "query": "What are the payment terms?"}
        4. Receive stream:
               {"type": "retrieving", ...}
               {"type": "sources",    "data": [{chunk}, ...]}
               {"type": "generating", ...}
               {"type": "token",      "data": {"text": "The"}}
               {"type": "token",      "data": {"text": " payment"}}
               ...
               {"type": "done",       "data": {"total_tokens": 312}}
        5. Send another query (multi-turn) or disconnect.
    """
    if _pipeline is None:
        await websocket.accept()
        await websocket.send_json({"type": "error", "data": {"message": "Service not ready."}})
        await websocket.close()
        return
    await handle_rag_websocket(websocket, _pipeline)


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "rag_service.start_rag:app",
        host=settings.WS_HOST,
        port=settings.WS_PORT,
        reload=False,
        log_level="info",
    )
