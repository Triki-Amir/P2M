"""
RAG Service — Ollama Streaming Generator
Streams llama3 tokens from a local Ollama instance via async HTTP.
"""

import json
import logging
from typing import AsyncIterator

import httpx

from .config import RAGSettings
from .models import SourceChunk

logger = logging.getLogger(__name__)


class OllamaGenerator:

    def __init__(self, settings: RAGSettings):
        self.cfg = settings
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.cfg.OLLAMA_BASE_URL,
            timeout=httpx.Timeout(self.cfg.OLLAMA_TIMEOUT),
        )
        logger.info("OllamaGenerator: client ready → %s", self.cfg.OLLAMA_BASE_URL)

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()

    def build_prompt(
        self,
        query: str,
        chunks: list[SourceChunk],
        history_context: str,
    ) -> str:
        context_parts: list[str] = []
        total_chars = 0
        for i, chunk in enumerate(chunks, start=1):
            passage = (
                f"[{i}] (page: {chunk.metadata.get('page_index', '?')}, "
                f"type: {chunk.metadata.get('block_type', '?')})\n{chunk.content}"
            )
            if total_chars + len(passage) > self.cfg.MAX_CONTEXT_CHARS:
                break
            context_parts.append(passage)
            total_chars += len(passage)

        context_block = "\n\n".join(context_parts) or "No relevant passages found."

        history_block = (history_context + "\n") if history_context else ""

        return (
            f"{self.cfg.SYSTEM_PROMPT}\n\n"
            f"=== CONTEXT PASSAGES ===\n{context_block}\n\n"
            f"=== CONVERSATION ===\n{history_block}"
            f"USER: {query}\nASSISTANT:"
        )

    async def stream(
        self,
        query: str,
        chunks: list[SourceChunk],
        history_context: str,
    ) -> AsyncIterator[str]:
        if not self._client:
            raise RuntimeError("OllamaGenerator not connected. Call connect() first.")

        prompt = self.build_prompt(query, chunks, history_context)
        payload = {
            "model": self.cfg.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": self.cfg.OLLAMA_TEMPERATURE,
                "top_p": self.cfg.OLLAMA_TOP_P,
                "num_predict": self.cfg.OLLAMA_MAX_TOKENS,
            },
        }

        try:
            # Use a regular POST first to check status, then stream
            req = self._client.build_request("POST", "/api/generate", json=payload)
            response = await self._client.send(req, stream=True)

            if response.status_code != 200:
                await response.aread()
                raise RuntimeError(
                    f"Ollama returned HTTP {response.status_code}: {response.text}"
                )

            buffer = b""
            async for raw_chunk in response.aiter_bytes():
                buffer += raw_chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Unparseable line: %r", line)
                        continue

                    token = data.get("response", "")
                    if token:
                        yield token

                    if data.get("done", False):
                        await response.aclose()
                        return

            await response.aclose()

        except httpx.ConnectError:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.cfg.OLLAMA_BASE_URL}. "
                "Is Ollama running? Run: `ollama serve`"
            )

    async def check_model_available(self) -> bool:
        if not self._client:
            return False
        try:
            resp = await self._client.get("/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            available = any(self.cfg.OLLAMA_MODEL in m for m in models)
            if not available:
                logger.warning(
                    "Model '%s' not found. Available: %s",
                    self.cfg.OLLAMA_MODEL, models,
                )
            return available
        except Exception as exc:
            logger.error("Ollama health check failed: %s", exc)
            return False
