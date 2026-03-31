# NLP Pipeline Service

This service processes document text extracted by the OCR service into semantic chunks, detects their language, and prepares them for indexing.

## Purpose

- **Text Cleaning**: Normalizes whitespace, removes noise, and formats text for processing.
- **Language Detection**: Identifies whether sections are in French (FR), Arabic (AR), or English (EN).
- **Translation (Local AI)**: Uses `Helsinki-NLP` models via `transformers` to translate non-English text to English locally.
- **Paragraph-Based Chunking**: 
    - Respects boundaries detected by the OCR service.
    - Keeps paragraphs under **2000 characters** as single chunks for better semantic coherence.
    - Only splits extremely long paragraphs using a **200-character overlap**.

## Directory Structure

```text
nlp_pipeline_svc/
├── app/
│   ├── nlp/                  # Core NLP logic
│   │   ├── cleaning.py       # Text normalization
│   │   ├── chunker.py        # Semantic chunking
│   │   ├── language_detection.py # Lang ID
│   │   └── translation.py     # Translation logic
│   ├── pipeline.py           # Orchestrates the OCR → NLP flow
│   ├── config.py             # Service settings overrides
│   └── main.py              # RabbitMQ consumer / entry point
└── test_nlp.py               # Testing script
```

## How to Run

### Local Sequence Mode

1.  Place a document in the data folder.
2.  Run the OCR service: `python ocr_service/main.py path/to/document.pdf`
3.  Run the NLP service: `python nlp_pipeline_svc/app/main.py`
    *   This will consume `data/ocr_completed.json` and produce `data/nlp_completed.json`.

### Using the Pipeline Orchestrator

Run the entire pipeline in one go:
`python run_pipeline.py <path_to_pdf>`

## How to Test

Use the provided testing script to simulate OCR data and verify the NLP outputs:

`python nlp_pipeline_svc/test_nlp.py`

This script will:
1. Create a mock French OCR output in `data/ocr_completed.json`.
2. Run the NLP service to process it.
3. Print out the resulting semantic chunks and their translated text.

## Configuration

Settings can be overridden via environment variables or in `app/config.py`:
- `NLP_TARGET_LANG`: Target language for translation (default: 'en').
- `NLP_MAX_CHUNK_SIZE`: Maximum size of semantic chunks (default: 500).
- `NLP_CHUNK_OVERLAP`: Overlap between chunks (default: 50).
