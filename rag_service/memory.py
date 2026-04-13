"""
RAG Service Memory integration with LangChain.
"""
from langchain_postgres import PostgresChatMessageHistory
from langchain.memory import ConversationSummaryBufferMemory
from langchain_ollama import OllamaLLM
from psycopg_pool import ConnectionPool
import psycopg
from collections.abc import Generator

from .config import get_settings

class SummarizingPostgresMemory:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.settings = get_settings()
        
        # We need a sync connection pool for PostgresChatMessageHistory
        conn_info = (
            f"postgresql://{self.settings.POSTGRES_USER}:{self.settings.POSTGRES_PASSWORD}"
            f"@{self.settings.POSTGRES_HOST}:{self.settings.POSTGRES_PORT}/{self.settings.POSTGRES_DB}"
        )
        # Ensure the table exists
        self._ensure_table_exists(conn_info)
        
        self.pool = ConnectionPool(
            conninfo=conn_info,
            max_size=20,
        )
        
        self.chat_history = PostgresChatMessageHistory(
            self.settings.MEMORY_TABLE_NAME,
            self.session_id,
            sync_connection=self.pool,
        )
        
        # We use standard OllamaLLM for summarization with langchain
        self.llm = OllamaLLM(
            base_url=self.settings.OLLAMA_BASE_URL,
            model=self.settings.OLLAMA_MODEL
        )
        
        self.memory = ConversationSummaryBufferMemory(
            llm=self.llm,
            chat_memory=self.chat_history,
            max_token_limit=self.settings.MEMORY_MAX_TOKENS,
            return_messages=True
        )

    def _ensure_table_exists(self, conn_info: str):
        # The schema expected by PostgresChatMessageHistory:
        # id (serial primary key), session_id (text), message (jsonb)
        table_name = self.settings.MEMORY_TABLE_NAME
        try:
            with psycopg.connect(conn_info) as conn:
                with conn.cursor() as cur:
                    # Create table if not exists using langchain-postgres creation logic
                    # Or we can let PostgresChatMessageHistory handle it if pg is right
                    PostgresChatMessageHistory.create_sync_schema(conn, table_name)
                    conn.commit()
        except Exception as e:
            import logging
            logging.error(f"Error creating memory table: {e}")

    def get_history_context(self) -> str:
        """Loads memory variables and formats them as a string."""
        history = self.memory.load_memory_variables({})
        messages = history.get("history", [])
        
        if not messages:
            return ""
            
        formatted_messages = []
        for msg in messages:
            role = "User" if msg.type == "human" else "Assistant" if msg.type == "ai" else "System"
            formatted_messages.append(f"{role}: {msg.content}")
            
        return "\n".join(formatted_messages)
        
    def save_context(self, user_query: str, ai_response: str):
        """Saves current turn to history and triggers summarization if needed."""
        self.memory.save_context(
            {"input": user_query},
            {"output": ai_response}
        )
