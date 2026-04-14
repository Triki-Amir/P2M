"""
RAG Service — Conversation Memory
Uses langchain_postgres.PostgresChatMessageHistory directly.
Sliding window approach — keeps last N exchanges, no summarization LLM needed.
"""

import logging
import psycopg
from langchain_postgres import PostgresChatMessageHistory
from langchain_core.messages import HumanMessage, AIMessage

from .config import get_settings

logger = logging.getLogger(__name__)


class ConversationMemory:
    """
    Persists conversation history in PostgreSQL using langchain_postgres.

    Strategy: sliding window — keeps the last MAX_EXCHANGES turns.
    Simple, fast, no extra LLM call for summarization.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.settings = get_settings()
        self._conn_info = (
            f"postgresql://{self.settings.POSTGRES_USER}:{self.settings.POSTGRES_PASSWORD}"
            f"@{self.settings.POSTGRES_HOST}:{self.settings.POSTGRES_PORT}/{self.settings.POSTGRES_DB}"
        )
        self._ensure_table()
        self._history = self._build_history()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _ensure_table(self) -> None:
        """Create the chat history table if it doesn't exist."""
        try:
            with psycopg.connect(self._conn_info) as conn:
                PostgresChatMessageHistory.create_sync_schema(
                    conn, self.settings.MEMORY_TABLE_NAME
                )
                conn.commit()
        except Exception as exc:
            logger.error("Memory: failed to create table: %s", exc)

    def _build_history(self) -> PostgresChatMessageHistory:
        """Build a sync PostgresChatMessageHistory instance."""
        conn = psycopg.connect(self._conn_info)
        return PostgresChatMessageHistory(
            self.settings.MEMORY_TABLE_NAME,
            self.session_id,
            sync_connection=conn,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def get_history_context(self) -> str:
        """
        Returns the last N exchanges formatted as a string for the prompt.
        Empty string if no history exists yet.
        """
        try:
            messages = self._history.messages
            if not messages:
                return ""

            # Keep only last MAX_EXCHANGES * 2 messages (each exchange = 2 messages)
            max_msgs = self.settings.MEMORY_MAX_EXCHANGES * 2
            recent = messages[-max_msgs:]

            lines = []
            for msg in recent:
                if isinstance(msg, HumanMessage):
                    lines.append(f"User: {msg.content}")
                elif isinstance(msg, AIMessage):
                    lines.append(f"Assistant: {msg.content}")

            return "\n".join(lines)

        except Exception as exc:
            logger.error("Memory: failed to load history: %s", exc)
            return ""

    def save_turn(self, user_query: str, ai_response: str) -> None:
        """Save one user+assistant exchange to PostgreSQL."""
        try:
            self._history.add_user_message(user_query)
            self._history.add_ai_message(ai_response)
        except Exception as exc:
            logger.error("Memory: failed to save turn: %s", exc)

    def clear(self) -> None:
        """Clear all history for this session."""
        try:
            self._history.clear()
        except Exception as exc:
            logger.error("Memory: failed to clear history: %s", exc)