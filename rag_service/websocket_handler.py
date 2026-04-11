"""
RAG Service — WebSocket Handler
Manages the WebSocket lifecycle: handshake → receive query → stream pipeline events.
Each connection gets an isolated session; multiple concurrent sessions are supported.
"""

import json
import logging
import uuid
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from .models import QueryMessage, WSMessage
from .pipeline import RAGPipeline

logger = logging.getLogger(__name__)


class RAGSession:
    """Represents a single active WebSocket connection."""

    def __init__(self, websocket: WebSocket, pipeline: RAGPipeline):
        self.ws = websocket
        self.pipeline = pipeline
        self.session_id = str(uuid.uuid4())[:8]

    async def send(self, message: WSMessage) -> None:
        """Serialise and send a WSMessage. Silently drops if socket is closed."""
        try:
            await self.ws.send_text(message.model_dump_json())
        except Exception:
            pass  # connection already closed

    async def run(self) -> None:
        """
        Main session loop:
            1. Accept connection and send READY.
            2. Wait for a QueryMessage.
            3. Run the RAG pipeline, streaming events back.
            4. Loop back to step 2 (multi-turn within same connection).
        """
        await self.ws.accept()
        logger.info("[%s] WebSocket connected.", self.session_id)
        await self.send(WSMessage.ready())

        try:
            while True:
                raw = await self.ws.receive_text()
                query_msg = self._parse_message(raw)

                if query_msg is None:
                    continue  # error already sent

                logger.info(
                    "[%s] Query received | doc=%s | query='%s...'",
                    self.session_id,
                    query_msg.document_id,
                    query_msg.query[:60],
                )

                # Stream all pipeline events back to the client
                async for event in self.pipeline.run(query_msg):
                    await self.send(event)

        except WebSocketDisconnect:
            logger.info("[%s] Client disconnected.", self.session_id)
        except Exception as exc:
            logger.exception("[%s] Unhandled session error: %s", self.session_id, exc)
            await self.send(WSMessage.error("Unexpected server error.", code="INTERNAL_ERROR"))

    def _parse_message(self, raw: str) -> QueryMessage | None:
        """Parse raw JSON into a QueryMessage; send ERROR if invalid."""
        try:
            data: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[%s] Invalid JSON received.", self.session_id)
            # fire-and-forget (we're not in an async context here)
            import asyncio
            asyncio.create_task(
                self.send(WSMessage.error("Invalid JSON payload.", code="PARSE_ERROR"))
            )
            return None

        try:
            return QueryMessage(**data)
        except ValidationError as exc:
            errors = exc.errors()
            msg = "; ".join(f"{e['loc'][-1]}: {e['msg']}" for e in errors)
            import asyncio
            asyncio.create_task(
                self.send(WSMessage.error(f"Schema error: {msg}", code="VALIDATION_ERROR"))
            )
            return None


async def handle_rag_websocket(websocket: WebSocket, pipeline: RAGPipeline) -> None:
    """
    Entry point called by the FastAPI WebSocket route.

    Usage in start_rag.py:
        @app.websocket("/rag/ws")
        async def ws_endpoint(websocket: WebSocket):
            await handle_rag_websocket(websocket, pipeline)
    """
    session = RAGSession(websocket=websocket, pipeline=pipeline)
    await session.run()
