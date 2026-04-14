"""
RAG Service — Conversation Memory
Uses langchain_postgres.PostgresChatMessageHistory with sliding window.
"""

import logging
import psycopg
from langchain_postgres import PostgresChatMessageHistory
from langchain_core.messages import HumanMessage, AIMessage

from .config import get_settings

logger = logging.getLogger(__name__)

# SQL to create the chat history table manually
# (compatible with all langchain-postgres versions)
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {table_name} (
    id          BIGSERIAL PRIMARY KEY,
    session_id  TEXT      NOT NULL,
    message     JSONB     NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_{table_name}_session
    ON {table_name} (session_id);
"""


class ConversationMemory:
    """
    Persists conversation history in PostgreSQL.
    Sliding window — keeps the last MEMORY_MAX_EXCHANGES turns.
    """

    def __init__(self, session_id: str):
        self.session_id   = session_id
        self.settings     = get_settings()
        self._conn_info   = (
            f"postgresql://{self.settings.POSTGRES_USER}:{self.settings.POSTGRES_PASSWORD}"
            f"@{self.settings.POSTGRES_HOST}:{self.settings.POSTGRES_PORT}/{self.settings.POSTGRES_DB}"
        )
        self._table       = self.settings.MEMORY_TABLE_NAME
        self._ensure_table()
        self._history     = self._build_history()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _ensure_table(self) -> None:
        """Create the chat history table if it doesn't exist."""
        try:
            with psycopg.connect(self._conn_info) as conn:
                conn.execute(
                    CREATE_TABLE_SQL.format(table_name=self._table)
                )
                conn.commit()
        except Exception as exc:
            logger.error("Memory: failed to create table: %s", exc)

    def _build_history(self) -> PostgresChatMessageHistory:
        """Build a PostgresChatMessageHistory instance."""
        try:
            conn = psycopg.connect(self._conn_info)
            return PostgresChatMessageHistory(
                self._table,
                self.session_id,
                sync_connection=conn,
            )
        except Exception as exc:
            logger.error("Memory: failed to build history: %s", exc)
            return None

    # ── Public API ────────────────────────────────────────────────────────────

    def get_history_context(self) -> str:
        """
        Returns the last N exchanges formatted as a string for the prompt.
        Returns empty string if no history or on error.
        """
        if not self._history:
            return ""
        try:
            messages = self._history.messages
            if not messages:
                return ""

            # Keep last MAX_EXCHANGES * 2 messages
            max_msgs = self.settings.MEMORY_MAX_EXCHANGES * 2
            recent   = messages[-max_msgs:]

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
        """Save one user + assistant exchange to PostgreSQL."""
        if not self._history:
            return
        try:
            self._history.add_user_message(user_query)
            self._history.add_ai_message(ai_response)
            logger.debug("Memory: saved turn for session=%s", self.session_id)
        except Exception as exc:
            logger.error("Memory: failed to save turn: %s", exc)

    def clear(self) -> None:
        """Clear all history for this session."""
        if not self._history:
            return
        try:
            self._history.clear()
        except Exception as exc:
            logger.error("Memory: failed to clear: %s", exc)