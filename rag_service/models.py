"""
RAG Service — Pydantic Models
Defines all WebSocket message schemas (inbound and outbound).
"""

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


# ── Inbound (Client → Server) ─────────────────────────────────────────────────

class QueryMessage(BaseModel):
    """Initial query sent by the client to start a RAG session."""
    document_id: str = Field(..., description="UUID of the document to query against")
    query: str = Field(..., min_length=1, max_length=2000, description="User question")
    conversation_history: list[dict[str, str]] = Field(
        default_factory=list,
        description="Optional prior turns: [{'role': 'user'|'assistant', 'content': '...'}]"
    )


# ── Outbound (Server → Client) ────────────────────────────────────────────────

class MessageType(str, Enum):
    # Lifecycle
    READY       = "ready"         # connection established
    RETRIEVING  = "retrieving"    # fetching chunks
    GENERATING  = "generating"    # LLM started

    # Streaming content
    TOKEN       = "token"         # single streamed token
    DONE        = "done"          # generation complete

    # Metadata
    SOURCES     = "sources"       # retrieved source chunks
    ERROR       = "error"         # error occurred


class SourceChunk(BaseModel):
    """A single retrieved document chunk sent back as a citation source."""
    chunk_id: str
    document_id: str
    content: str
    score: float = Field(description="Fused RRF score (higher = more relevant)")
    metadata: dict[str, Any] = Field(default_factory=dict)


class WSMessage(BaseModel):
    """Envelope for every message the server sends over WebSocket."""
    type: MessageType
    data: Any = None              # payload varies by type

    @classmethod
    def ready(cls) -> "WSMessage":
        return cls(type=MessageType.READY, data={"message": "Connected. Send your query."})

    @classmethod
    def retrieving(cls, document_id: str, query: str) -> "WSMessage":
        return cls(type=MessageType.RETRIEVING, data={"document_id": document_id, "query": query})

    @classmethod
    def generating(cls) -> "WSMessage":
        return cls(type=MessageType.GENERATING, data={"message": "Generating answer..."})

    @classmethod
    def token(cls, text: str) -> "WSMessage":
        return cls(type=MessageType.TOKEN, data={"text": text})

    @classmethod
    def sources(cls, chunks: list[SourceChunk]) -> "WSMessage":
        return cls(type=MessageType.SOURCES, data=[c.model_dump() for c in chunks])

    @classmethod
    def done(cls, total_tokens: int = 0) -> "WSMessage":
        return cls(type=MessageType.DONE, data={"total_tokens": total_tokens})

    @classmethod
    def error(cls, message: str, code: str = "INTERNAL_ERROR") -> "WSMessage":
        return cls(type=MessageType.ERROR, data={"message": message, "code": code})
