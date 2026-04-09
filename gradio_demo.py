"""
gradio_demo.py
──────────────
Small Gradio demo for the P2M NLP pipeline.

This app accepts OCR JSON, parses it into the shared OcrDocument schema,
extracts document metadata, and previews the detected blocks.

Run:
    c:/Users/mradn/OneDrive/Desktop/P2M/P2M/.venv/Scripts/python.exe gradio_demo.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import gradio as gr

from shared.models import OcrDocument
from nlp_pipeline_svc.app.nlp.metadata_extractor import extract_metadata


PROJECT_ROOT = Path(__file__).resolve().parent
SAMPLE_OCR_PATH = PROJECT_ROOT / "data" / "ocr_completed.json"


def _load_ocr_payload(uploaded_file, pasted_json: str) -> dict[str, Any]:
    if uploaded_file is not None:
        raw_text = Path(uploaded_file).read_text(encoding="utf-8")
        return json.loads(raw_text)

    if pasted_json and pasted_json.strip():
        return json.loads(pasted_json)

    if SAMPLE_OCR_PATH.exists():
        return json.loads(SAMPLE_OCR_PATH.read_text(encoding="utf-8"))

    raise ValueError("Upload an OCR JSON file or paste JSON into the textbox.")


def analyze_ocr(uploaded_file, pasted_json: str):
    try:
        payload = _load_ocr_payload(uploaded_file, pasted_json)
        ocr_doc = OcrDocument(**payload)
        metadata = extract_metadata(ocr_doc)

        block_rows = []
        for page in ocr_doc.pages:
            for block_index, block in enumerate(page.blocks):
                block_rows.append(
                    {
                        "page_index": page.page_index,
                        "block_index": block_index,
                        "type": block.type,
                        "text_preview": block.text[:180],
                        "section_title": block.section_title,
                        "context": block.context,
                    }
                )

        summary = {
            "doc_id": ocr_doc.doc_id,
            "page_count": len(ocr_doc.pages),
            "block_count": len(block_rows),
            "source_lang": ocr_doc.source_lang,
        }

        return (
            json.dumps(metadata, indent=2, ensure_ascii=False),
            json.dumps(summary, indent=2, ensure_ascii=False),
            [
                [
                    row["page_index"],
                    row["block_index"],
                    row["type"],
                    row["text_preview"],
                    row["section_title"],
                    row["context"],
                ]
                for row in block_rows
            ],
            f"Processed {ocr_doc.doc_id} successfully.",
        )
    except Exception as exc:
        return (
            json.dumps({"error": str(exc)}, indent=2, ensure_ascii=False),
            json.dumps({}, indent=2, ensure_ascii=False),
            [],
            f"Error: {exc}",
        )


with gr.Blocks(
    title="P2M OCR to NLP Demo",
    theme=gr.themes.Soft(primary_hue="orange", secondary_hue="amber"),
) as demo:
    gr.Markdown(
        """
        # P2M OCR to NLP Demo

        Upload an OCR JSON file or paste OCR JSON directly. The app extracts
        document metadata from the OCR payload and previews the detected blocks.
        """
    )

    with gr.Row():
        uploaded_file = gr.File(label="OCR JSON file", file_types=[".json"], type="filepath")
        pasted_json = gr.Textbox(
            label="Or paste OCR JSON",
            lines=16,
            placeholder="Paste the contents of an OCR JSON document here...",
        )

    analyze_button = gr.Button("Analyze OCR JSON", variant="primary")
    status = gr.Markdown()

    with gr.Row():
        metadata_output = gr.Code(label="Document Metadata", language="json")
        summary_output = gr.Code(label="Document Summary", language="json")

    blocks_output = gr.Dataframe(
        label="OCR Block Preview",
        headers=["page_index", "block_index", "type", "text_preview", "section_title", "context"],
        interactive=False,
        wrap=True,
    )

    analyze_button.click(
        fn=analyze_ocr,
        inputs=[uploaded_file, pasted_json],
        outputs=[metadata_output, summary_output, blocks_output, status],
    )

    gr.Examples(
        examples=[[str(SAMPLE_OCR_PATH), ""]],
        inputs=[uploaded_file, pasted_json],
        label="Sample OCR JSON",
    )


if __name__ == "__main__":
    demo.launch()