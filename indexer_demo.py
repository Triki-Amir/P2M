"""
indexer_demo.py
───────────────
Gradio demo for the P2M Indexer service.

This app accepts an NLP JSON file (NlpDocument), generates embeddings 
(dense & sparse) using the BGE-M3 model, and optionally connects to the 
PostgreSQL database to verify the indexing state.

Run:
    python indexer_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import gradio as gr
import numpy as np

# Ensure project root is in path for imports
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from shared.models import NlpDocument
from indexer_svc.app.embedder import Embedder, ChunkEmbedding
from indexer_svc.app.store import VectorStore
from indexer_svc.app import config


def analyze_nlp_json(uploaded_file, pasted_json: str, do_index: bool):
    try:
        # 1. Load Data
        if uploaded_file is not None:
            raw_text = Path(uploaded_file).read_text(encoding="utf-8")
            payload = json.loads(raw_text)
        elif pasted_json and pasted_json.strip():
            payload = json.loads(pasted_json)
        else:
            sample_path = PROJECT_ROOT / "data" / "nlp_completed.json"
            if sample_path.exists():
                payload = json.loads(sample_path.read_text(encoding="utf-8"))
            else:
                return None, None, [], "Error: Please upload an NLP JSON or paste content."

        nlp_doc = NlpDocument(**payload)
        
        # 2. Embedding Process
        embedder = Embedder(config.EMBEDDING_MODEL, batch_size=4) # Small batch for demo
        texts = [c.text_en for c in nlp_doc.chunks]
        chunk_ids = [c.chunk_id for c in nlp_doc.chunks]
        
        status_msg = f"Generating embeddings for {len(texts)} chunks..."
        embeddings = embedder.embed(texts, chunk_ids)
        
        # 3. DB Insertion (Optional)
        indexing_result = "Skipped"
        if do_index:
            try:
                with VectorStore(dsn=config.DB_DSN) as store:
                    n = store.upsert_chunks(
                        chunks=nlp_doc.chunks,
                        embeddings=embeddings,
                        doc_id=nlp_doc.doc_id,
                    )
                indexing_result = f"Success ({n} chunks upserted)"
            except Exception as db_exc:
                indexing_result = f"DB Error: {str(db_exc)}"

        # 4. Prepare Outputs
        block_rows = []
        for i, (chunk, emb) in enumerate(zip(nlp_doc.chunks, embeddings)):
            # Sample some sparse weights for display
            sparse_sample = dict(list(emb.sparse_vec.items())[:5])
            block_rows.append([
                chunk.page_index,
                chunk.block_index,
                chunk.block_type,
                chunk.text_original[:100] + "...",
                f"Dense ({len(emb.dense_vec)})",
                str(sparse_sample) + "..."
            ])

        summary = {
            "doc_id": nlp_doc.doc_id,
            "chunks_count": len(nlp_doc.chunks),
            "embedding_model": config.EMBEDDING_MODEL,
            "indexing_status": indexing_result,
            "vector_dimension": len(embeddings[0].dense_vec) if embeddings else 0
        }

        return (
            json.dumps(summary, indent=2),
            block_rows,
            f"Processed {nlp_doc.doc_id} successfully. Indexing: {indexing_result}"
        )

    except Exception as e:
        return json.dumps({"error": str(e)}), [], f"Error: {str(e)}"


with gr.Blocks(
    title="P2M Indexer Demo",
    theme=gr.themes.Soft(primary_hue="green", secondary_hue="emerald"),
) as demo:
    gr.Markdown(
        """
        # 🗄️ P2M Indexer Service Demo
        
        This demo simulates the final stage of the pipeline:
        1. **Load** the translated English text from the NLP service.
        2. **Embed** chunks using **BGE-M3** (Dense + Sparse vectors).
        3. **Store** (Optional) the results in the PostgreSQL/pgvector database.
        """
    )

    with gr.Row():
        with gr.Column(scale=1):
            uploaded_file = gr.File(label="NLP JSON file", file_types=[".json"])
            pasted_json = gr.Textbox(label="Or paste NLP JSON", lines=10)
            do_index_cb = gr.Checkbox(label="Upsert to Database (pgvector)", value=False)
            run_btn = gr.Button("Generate Embeddings & Index", variant="primary")
        
        with gr.Column(scale=2):
            summary_output = gr.JSON(label="Indexing Summary")
            status_output = gr.Markdown()

    blocks_table = gr.Dataframe(
        headers=["Page", "Block", "Type", "Text (Original)", "Dense Vector", "Sparse Sample"],
        label="Chunk Embedding Preview",
        interactive=False
    )

    run_btn.click(
        fn=analyze_nlp_json,
        inputs=[uploaded_file, pasted_json, do_index_cb],
        outputs=[summary_output, blocks_table, status_output]
    )

    gr.Examples(
        examples=[[str(PROJECT_ROOT / "data" / "nlp_completed.json"), "", False]],
        inputs=[uploaded_file, pasted_json, do_index_cb],
        label="Sample NLP Output"
    )

if __name__ == "__main__":
    demo.launch()
