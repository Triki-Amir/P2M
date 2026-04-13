"""
RAG Service — Pipeline Orchestrator
Wires the HybridRetriever and OllamaGenerator together.
Yields typed WSMessage objects so the WebSocket handler stays thin.
"""

import logging
from typing import AsyncIterator

from .config import RAGSettings
from .generator import OllamaGenerator
from .models import QueryMessage, SourceChunk, WSMessage
from .retriever import HybridRetriever

logger = logging.getLogger(__name__)


class RAGPipeline:
    """
    High-level pipeline:
        retrieve → build prompt → stream generate → yield events

    The caller (WebSocket handler) iterates over `run()` and serialises
    each WSMessage to JSON before sending it over the wire.
    """

    def __init__(self, retriever: HybridRetriever, generator: OllamaGenerator):
        self.retriever = retriever
        self.generator = generator

    async def run(self, message: QueryMessage) -> AsyncIterator[WSMessage]:
        """
        Async generator of WSMessage events:
            RETRIEVING → SOURCES → GENERATING → TOKEN … TOKEN → DONE
            (or ERROR on failure at any stage)
        """
        # ── Stage 1: Announce retrieval ───────────────────────────────────
        yield WSMessage.retrieving(message.document_id, message.query)

        # ── Stage 2: Hybrid retrieval ─────────────────────────────────────
        try:
            chunks: list[SourceChunk] = await self.retriever.retrieve(
                query=message.query,
                document_id=message.document_id,
            )
        except Exception as exc:
            logger.exception("Retrieval failed: %s", exc)
            yield WSMessage.error(f"Retrieval failed: {exc}", code="RETRIEVAL_ERROR")
            return

        if not chunks:
            yield WSMessage.error(
                "No relevant passages found for this document and query.",
                code="NO_RESULTS",
            )
            return

        # ── Stage 3: Send sources to client ───────────────────────────────
        yield WSMessage.sources(chunks)

        # ── Stage 4: Fetch Conversation Memory ────────────────────────────
        try:
            from .memory import SummarizingPostgresMemory
            memory = SummarizingPostgresMemory(session_id=message.session_id)
            history_context = memory.get_history_context()
        except Exception as exc:
            logger.exception("Failed to load conversation history: %s", exc)
            history_context = ""

        # ── Stage 5: Announce generation ──────────────────────────────────
        yield WSMessage.generating()

        # ── Stage 6: Stream tokens ────────────────────────────────────────
        token_count = 0
        full_response = []
        try:
            async for token in self.generator.stream(
                query=message.query,
                chunks=chunks,
                history_context=history_context,
            ):
                full_response.append(token)
                yield WSMessage.token(token)
                token_count += 1
                
            try:
                # Save this turn automatically
                from .memory import SummarizingPostgresMemory
                memory = SummarizingPostgresMemory(session_id=message.session_id)
                memory.save_context(user_query=message.query, ai_response="".join(full_response))
            except Exception as e:
                logger.error("Failed to save conversation history: %s", e)

        except RuntimeError as exc:
            logger.error("Generation error: %s", exc)
            yield WSMessage.error(str(exc), code="GENERATION_ERROR")
            return
        except Exception as exc:
            logger.exception("Unexpected generation error: %s", exc)
            yield WSMessage.error("Unexpected error during generation.", code="INTERNAL_ERROR")
            return

        # ── Stage 6: Done ─────────────────────────────────────────────────
        yield WSMessage.done(total_tokens=token_count)
        logger.info(
            "RAG complete | doc=%s | tokens=%d | chunks=%d",
            message.document_id, token_count, len(chunks),
        )


async def build_pipeline(settings: RAGSettings, embed_fn) -> RAGPipeline:
    """
    Factory: initialises retriever + generator and returns a ready pipeline.
    Call once at startup and reuse across all WebSocket sessions.

    Args:
        settings:  RAGSettings instance.
        embed_fn:  Async callable (query: str) -> list[float].
                   Must match the embedding model used by your Indexer.
    """
    retriever = HybridRetriever(settings=settings, embed_fn=embed_fn)
    await retriever.connect()

    generator = OllamaGenerator(settings=settings)
    await generator.connect()

    # Optional but helpful: warn if model not pulled
    model_ok = await generator.check_model_available()
    if not model_ok:
        logger.warning(
            "⚠  Model '%s' not found in Ollama. "
            "Run: ollama pull %s",
            settings.OLLAMA_MODEL, settings.OLLAMA_MODEL,
        )

    return RAGPipeline(retriever=retriever, generator=generator)
