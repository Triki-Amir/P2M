"""
run_pipeline.py
────────────────
Local orchestrator — runs all services in sequence.

Usage:
    python run_pipeline.py path/to/document.pdf

When you move to microservices, this file becomes the only thing
that changes: replace direct function calls with HTTP/queue triggers.
Each service stays completely identical.
"""
import os
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
import sys
from pathlib import Path
from indexer_svc.app.main import run_indexer
from ocr_service.main import run as run_ocr
from nlp_pipeline_svc.app.main import run_consumer as run_nlp
# from indexer_service.main import run as run_indexer  # uncomment when built


def main(pdf_path: str) -> None:
    print("=" * 60)
    print("  P2M Pipeline")
    print("=" * 60)

    run_ocr(pdf_path)
    run_nlp()           # reads data/ocr_completed.json automatically
    run_indexer()       # reads data/nlp_completed.json automatically

    print("=" * 60)
    print("  Pipeline complete")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_pipeline.py <path_to_pdf>")
        sys.exit(1)
    main(sys.argv[1])
