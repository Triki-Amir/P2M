"""
rag_demo.py
───────────
Gradio demo for the P2M RAG Service.

This app allows you to chat with your documents by:
1.  Retrieving relevant context from pgvector using Hybrid Retrieval.
2.  Generating answers using Ollama (Llama 3 / Mistral).
3.  Displaying the source chunks used for the answer.

Run:
    python rag_demo.py
"""

import asyncio
import sys
import uuid
from pathlib import Path
from typing import List, Tuple

import gradio as gr

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# RAG Service Imports
from rag_service.config import RAGSettings
from rag_service.generator import OllamaGenerator
from rag_service.retriever import HybridRetriever
from rag_service.pipeline import RAGPipeline
from rag_service.models import QueryMessage, WSMessage


# --- Backend Logic ---

class RAGDemoHandler:
    def __init__(self):
        self.settings = RAGSettings()
        self.retriever = HybridRetriever(
            embedder_model=self.settings.EMBEDDING_MODEL,
            db_dsn=self.settings.DB_DSN,
            top_k=self.settings.RETRIEVAL_TOP_K
        )
        self.generator = OllamaGenerator(
            base_url=self.settings.OLLAMA_BASE_URL,
            model_name=self.settings.OLLAMA_MODEL_NAME
        )
        self.pipeline = RAGPipeline(self.retriever, self.generator)
        self.session_id = str(uuid.uuid4())

    async def chat(self, message: str, history: List[Tuple[str, str]], doc_id: str):
        # Create QueryMessage
        query_msg = QueryMessage(
            query=message,
            document_id=doc_id if doc_id else None,
            session_id=self.session_id
        )

        response_text = ""
        sources_html = ""
        
        # Run Pipeline
        async for ws_msg in self.pipeline.run(query_msg):
            if ws_msg.type == "token":
                response_text += ws_msg.payload
                yield response_text, sources_html
            
            elif ws_msg.type == "sources":
                chunks = ws_msg.payload
                sources_html = "### 📚 Source Contexts\n"
                for i, chunk in enumerate(chunks):
                    sources_html += f"**Source {i+1} (Page {chunk.page_index})**\n"
                    sources_html += f"> {chunk.text_original[:300]}...\n\n"
                yield response_text, sources_html

            elif ws_msg.type == "error":
                response_text = f"❌ **Error:** {ws_msg.payload}"
                yield response_text, sources_html
                break

handler = RAGDemoHandler()

# --- Gradio UI ---

def wrapper(message, history, doc_id):
    # Use sync wrapper for async generator
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    gen = handler.chat(message, history, doc_id)
    
    try:
        while True:
            # We use a trick to run the async generator in Gradio's sync context
            # or we can use the 'gr.ChatInterface' which handles streaming better
            # but since we want to show sources separately, we do this:
            res = loop.run_until_complete(gen.__anext__())
            yield res
    except StopAsyncIteration:
        pass
    finally:
        loop.close()

with gr.Blocks(
    title="P2M RAG Chatbot",
    theme=gr.themes.Soft(primary_hue="orange", secondary_hue="amber"),
) as demo:
    gr.Markdown(
        """
        # 🤖 P2M RAG Service Chatbot
        
        Ask questions about your indexed documents. The system uses **Hybrid Retrieval** (Dense + Sparse) 
        to find context and **Ollama** to generate precise answers.
        """
    )

    with gr.Row():
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(label="Conversation", height=500)
            msg_input = gr.Textbox(
                label="Your Question",
                placeholder="Ex: Quelle est la date limite de soumission ?",
                show_label=False
            )
            with gr.Row():
                submit_btn = gr.Button("Send", variant="primary")
                clear_btn = gr.Button("Clear Chat")
        
        with gr.Column(scale=2):
            doc_id_input = gr.Textbox(
                label="Document Filter (doc_id)",
                placeholder="test_mi_parcours.pdf (Optionnel)",
                value="test_mi_parcours.pdf"
            )
            sources_box = gr.Markdown(label="Sources Used", value="*Sources will appear here...*")

    def user_msg(user_input, history):
        return "", history + [[user_input, None]]

    def bot_res(history, doc_id):
        user_message = history[-1][0]
        # Custom generator for chatbot history update
        chat_gen = handler.chat(user_message, history[:-1], doc_id)
        
        async def run_chat():
            async for text, sources in chat_gen:
                history[-1][1] = text
                yield history, sources

        # Handle async in Gradio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            gen = run_chat()
            while True:
                h, s = loop.run_until_complete(gen.__anext__())
                yield h, s
        except StopAsyncIteration:
            pass
        finally:
            loop.close()

    submit_btn.click(user_msg, [msg_input, chatbot], [msg_input, chatbot], queue=False).then(
        bot_res, [chatbot, doc_id_input], [chatbot, sources_box]
    )
    
    msg_input.submit(user_msg, [msg_input, chatbot], [msg_input, chatbot], queue=False).then(
        bot_res, [chatbot, doc_id_input], [chatbot, sources_box]
    )

    clear_btn.click(lambda: (None, [], "*Sources will appear here...*"), None, [msg_input, chatbot, sources_box])

if __name__ == "__main__":
    # Ensure Ollama is running or inform the user
    demo.queue().launch()
