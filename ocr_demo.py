"""
ocr_demo.py
───────────
Gradio demo for the P2M OCR pipeline.

This app accepts a PDF file, runs it through the OCR service (API or local fallback),
and displays the extracted blocks and structured JSON.

Run:
    python ocr_demo.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import gradio as gr

from shared.models import OcrDocument
from ocr_service.paddle_ocr import ocr_pdf_via_api, ocr_image
from ocr_service.pdf_to_images import pdf_to_images, cleanup_images


def process_pdf(pdf_file):
    if pdf_file is None:
        return None, None, "Please upload a PDF file."
    
    pdf_path = Path(pdf_file.name)
    doc_id = pdf_path.name
    
    try:
        # Step 1: Try API first
        pages = ocr_pdf_via_api(pdf_path)
        
        if pages is None:
            # Fallback to local
            image_paths = pdf_to_images(pdf_path)
            pages = []
            for page_index, image_path in enumerate(image_paths):
                page = ocr_image(image_path, page_index)
                pages.append(page)
            cleanup_images(image_paths)
            method = "Local Fallback"
        else:
            method = "Cloud API"

        ocr_doc = OcrDocument(
            doc_id=doc_id,
            source_lang=None, # Will be detected later in NLP
            pages=pages
        )

        # Prepare summary and table data
        block_rows = []
        for page in ocr_doc.pages:
            for block in page.blocks:
                block_rows.append([
                    page.page_index,
                    block.block_id,
                    block.block_label,
                    block.content_type,
                    block.plain_text[:200] + ("..." if len(block.plain_text) > 200 else ""),
                    "Yes" if block.is_nlp_relevant else "No"
                ])

        summary = {
            "document": doc_id,
            "method_used": method,
            "total_pages": len(ocr_doc.pages),
            "total_blocks": len(block_rows)
        }

        return (
            json.dumps(ocr_doc.model_dump(), indent=2, ensure_ascii=False),
            json.dumps(summary, indent=2, ensure_ascii=False),
            block_rows,
            f"Successfully processed {doc_id} using {method}."
        )

    except Exception as e:
        return None, None, [], f"Error: {str(e)}"


with gr.Blocks(
    title="P2M OCR Pipeline Demo",
    theme=gr.themes.Soft(primary_hue="blue", secondary_hue="slate"),
) as demo:
    gr.Markdown(
        """
        # 📄 P2M OCR Pipeline Demo
        
        Upload a PDF document to extract structured layout information using PaddleOCR.
        The system will attempt to use the **Cloud API** first, falling back to a **Local Model** if necessary.
        """
    )

    with gr.Row():
        with gr.Column(scale=1):
            pdf_input = gr.File(label="Upload PDF", file_types=[".pdf"])
            analyze_btn = gr.Button("Run OCR Extraction", variant="primary")
        
        with gr.Column(scale=2):
            status_output = gr.Textbox(label="Status", interactive=False)
            summary_output = gr.JSON(label="Execution Summary")

    with gr.Tabs():
        with gr.TabItem("Block Preview"):
            blocks_table = gr.Dataframe(
                headers=["Page", "ID", "Label", "Type", "Text Preview", "NLP Relevant"],
                datatype=["number", "number", "string", "string", "string", "string"],
                label="Extracted Layout Blocks"
            )
        
        with gr.TabItem("Raw JSON"):
            json_output = gr.Code(label="OcrDocument JSON", language="json")

    analyze_btn.click(
        fn=process_pdf,
        inputs=[pdf_input],
        outputs=[json_output, summary_output, blocks_table, status_output]
    )


if __name__ == "__main__":
    demo.launch()
