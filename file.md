# P2M Project Map for AI Models

## 1) What this repository is

P2M is a multi-service document intelligence system for PDF tenders.

Core objective:
1. Ingest PDF documents.
2. Extract structured text blocks (OCR).
3. Normalize, detect language, translate to English, and chunk (NLP).
4. Embed chunks and store vectors in PostgreSQL + pgvector (Indexer).
5. Support retrieval and future AI reasoning on indexed content.


## 2) Two active runtime modes (important)

This repo currently has two parallel integration styles:

### A. Local pipeline mode (file-based event bus)

Flow:
1. `ocr_service` writes `data/ocr_completed.json`.
2. `nlp_pipeline_svc` reads `ocr_completed`, writes `data/nlp_completed.json`.
3. `indexer_svc` reads `nlp_completed` and upserts vectors into `chunks` table.

Transport layer:
- `shared/event_bus.py`
- Event files in `data/`

Orchestration entrypoint:
- `run_pipeline.py`

### B. Async ingestion mode (API + RabbitMQ)

Flow:
1. Upload API stores PDF in MinIO and metadata in PostgreSQL (`documents`).
2. API publishes a message to RabbitMQ `ocr_queue`.
3. `rabbitmq_server/consumers/ocr_services.py` consumes, downloads PDF from MinIO, runs OCR -> NLP -> Indexer, then updates document status.

Current state:
- Queue flow executes real OCR/NLP/Indexer chain using the uploaded MinIO file.
- Indexer auto-creates pgvector `chunks` schema at runtime if missing.


## 3) High-level architecture

```text
                    (UI)
front-end (React) ------------------------------+
                                                |
                                                v
                                  minio_server/minio-backend (Node upload API, :3000)
                                                |
                                                v
                                              MinIO
                                                |
                                                v
                                            documents (Postgres)


FastAPI upload API (app/api.py, :8000) ---------+
      |                                         |
      v                                         v
    MinIO                                  RabbitMQ ocr_queue
      |                                         |
      +-----------------------------> OCR consumer (real pipeline)
                                                |
                                                v
                                   OCR -> NLP -> Indexer -> chunks
                                                |
                                                v
                                            documents updates


Local offline/processing chain:
OCR service -> data/ocr_completed.json -> NLP service -> data/nlp_completed.json -> Indexer -> chunks (pgvector)
```


## 4) Repository skeleton (AI-first view)

### Core backend and infra
- `app/`: FastAPI upload API + SQLAlchemy model for `documents`.
- `postgres_server/`: Docker + init SQL for `documents` and `chunks`.
- `minio_server/`: MinIO docker-compose.
- `rabbitmq_server/`: RabbitMQ docker-compose + producer/consumer scripts.
- `redis_server/`: Redis compose (present, not central in current main flow).

### Pipeline services
- `ocr_service/`: PDF -> page images -> OCR blocks -> `ocr_completed` event.
- `nlp_pipeline_svc/`: cleaning, language detection, translation, chunking -> `nlp_completed` event.
- `indexer_svc/`: bge-m3 dense+sparse embeddings + pgvector upsert into `chunks`.
- `shared/`: cross-service event bus and Pydantic contracts.

### Frontend and alternate upload backend
- `front-end/`: React/Vite UI.
- `minio_server/minio-backend/`: Node/Express upload backend used by UI (`/upload` on :3000).

### Coordination and verification
- `run_pipeline.py`: local sequential OCR -> NLP -> (indexer placeholder/comment).
- `verify_integration.py`: service connectivity check script.
- `ARCHITECTURE.md`, `INTEGRATION_TEST_GUIDE.md`, `VERIFICATION_CHECKLIST.md`: operational docs.


## 5) Canonical data contracts

### A) Shared event models (`shared/models.py`)

Main contracts:
- `OcrDocument`
  - `doc_id`
  - `source_lang`
  - `pages: list[OcrPage]`
- `OcrPage`
  - `page_index`
  - `blocks: list[OcrBlock]`
- `OcrBlock`
  - `type`, `text`, `bbox`, `section_title`, `context`
- `NlpDocument`
  - `doc_id`, `source_lang`, `chunks: list[NlpChunk]`
- `NlpChunk`
  - `chunk_id`, position indices, block type, language, text variants,
    metadata, bbox

### B) File event names (`shared/event_bus.py` and service configs)
- `ocr_completed` -> `data/ocr_completed.json`
- `nlp_completed` -> `data/nlp_completed.json`

### C) RabbitMQ message contract (`rabbitmq_server/Producers/ingestion.py`)
```json
{
  "doc_id": "<uuid>",
  "url": "http://<minio-endpoint>/<bucket>/<object>",
  "source": "user_upload"
}
```


## 6) Database schema that matters most

### A) `documents` table

Defined by:
- `postgres_server/init/01_documents.sql`
- mirrored in ORM: `app/models.py` (`Document`)

Purpose:
- Upload metadata, storage path, processing status, metadata JSON.

Typical status progression:
- `pending` (default at schema level)
- `uploaded`
- `processing`
- `completed`
- `failed`

### B) `chunks` table (pgvector)

Defined by:
- `postgres_server/init/02_chunks.sql`

Key fields:
- text: `text_original`, `text_en`
- metadata: `section_title`, `context`, `translation_failed`
- vectors: `dense_vec vector(1024)`, `sparse_vec sparsevec(250002)`

Indexes:
- HNSW dense index (`vector_ip_ops`)
- HNSW sparse index (`sparsevec_ip_ops`)
- B-tree on filtering columns (`doc_id`, `document_id`, `block_type`, `source_lang`)


## 7) Service responsibilities and code anchors

### FastAPI upload service
- Entry: `app/start_api.py`
- API: `app/api.py`
- DB session: `app/database.py`
- ORM model: `app/models.py`

Responsibilities:
1. Validate PDF.
2. Upload to MinIO bucket `pdf-storage`.
3. Insert `documents` row.
4. Publish queue message via `rabbitmq_server/Producers/ingestion.py`.
5. Move status to `processing` when queue publish succeeds.

### RabbitMQ producer/consumer
- Producer: `rabbitmq_server/Producers/ingestion.py`
- Consumer launcher: `rabbitmq_server/start_consumer.py`
- Consumer handler: `rabbitmq_server/consumers/ocr_services.py`

Responsibilities:
- Producer: push durable messages to `ocr_queue`.
- Consumer: download PDF from MinIO and run OCR -> NLP -> Indexer, then update `documents` status + metadata.

### OCR service (file-event mode)
- Entry: `ocr_service/main.py`
- Publish output: `ocr_service/output_writer.py`

Responsibilities:
1. Convert PDF to images.
2. OCR per page.
3. Build `OcrDocument`.
4. Publish `ocr_completed`.

### NLP service
- Entry: `nlp_pipeline_svc/app/main.py`
- Orchestrator: `nlp_pipeline_svc/app/pipeline.py`
- Config: `nlp_pipeline_svc/app/config.py`
- Modules: `nlp_pipeline_svc/app/nlp/`

Responsibilities:
1. Consume `ocr_completed`.
2. Clean text.
3. Detect language.
4. Translate to English.
5. Chunk by block-aware strategy.
6. Emit `NlpDocument` as `nlp_completed`.

### Indexer service
- Entry: `indexer_svc/app/main.py`
- Embedding: `indexer_svc/app/embedder.py`
- DB store: `indexer_svc/app/store.py`
- Config: `indexer_svc/app/config.py`

Responsibilities:
1. Consume `nlp_completed`.
2. Embed each chunk with `BAAI/bge-m3`.
3. Build dense + sparse vectors.
4. Resolve filename `doc_id` -> `documents.id` UUID.
5. Upsert into `chunks`.


## 8) Key cross-service joins and identifiers

There are two identifier styles in the project:

1. Upload/API domain:
- `documents.id` is UUID (primary key).

2. NLP/indexer file-event domain:
- `doc_id` often represents the original filename.

Bridge logic:
- `indexer_svc/app/store.py` resolves filename `doc_id` to `documents.id`
  by querying `documents.filename`.

Implication for AI agents:
- Always verify whether `doc_id` in a given context means UUID or filename.
- Do not assume one global meaning without checking call-site and transport.


## 9) Ports, credentials, and env defaults

### Ports
- FastAPI: `8000`
- Node upload backend: `3000`
- PostgreSQL: `5432`
- MinIO API: `9000`
- MinIO Console: `9001`
- RabbitMQ AMQP: `5672`
- RabbitMQ Management: `15672`

### Common defaults in repo
- Postgres: `postgres / 123456789`
- MinIO: `admin / password123` (Python flow) and `minioadmin / minioadmin` in some Node docs/examples
- RabbitMQ: `admin / secretpassword`

Note:
- There is config drift across docs and subprojects. Validate env values per service before running full-stack.


## 10) Typical run paths

### A) Local processing chain (file-event)
1. Ensure Python dependencies installed in root environment.
2. Run OCR service on a PDF (or `run_pipeline.py`).
3. Run NLP consumer (`nlp_pipeline_svc/app/main.py`).
4. Run indexer (`indexer_svc/app/main.py`).
5. Verify rows in `chunks`.

### B) Async ingestion chain (queue)
1. Start infra via docker-compose in:
   - `postgres_server/`
   - `minio_server/`
   - `rabbitmq_server/`
2. Start FastAPI (`app/start_api.py`).
3. Start consumer (`rabbitmq_server/start_consumer.py`).
4. Upload PDF to `POST /upload`.
5. Verify `documents` status transitions and queue activity.


## 11) Frontend integration notes

The React UI component `front-end/src/app/components/AIAgentSpace.tsx` currently posts files to:
- `http://localhost:3000/upload`

That targets Node backend in:
- `minio_server/minio-backend/server.js`

So there are two upload APIs in repo:
1. Python FastAPI (`:8000`, queue-integrated)
2. Node backend (`:3000`, MinIO + Postgres)

AI agents should not assume the frontend is currently wired to FastAPI unless code is changed.


## 12) Known integration gaps and risks

1. Queue worker currently runs OCR, NLP, and Indexer in one consumer process (simple and reliable, but not independently scalable per stage yet).
2. Config and docs have partial drift (paths, credentials, old assumptions).
3. Identifier semantics (`doc_id`) differ by stage and can cause join mistakes.


## 13) Minimal AI navigation guide

If an AI model must answer codebase questions quickly, inspect in this order:
1. `shared/models.py` (contracts)
2. `shared/event_bus.py` (transport abstraction)
3. `app/api.py` and `rabbitmq_server/*` (ingestion queue path)
4. `ocr_service/main.py` + `output_writer.py` (OCR output)
5. `nlp_pipeline_svc/app/pipeline.py` (NLP transformation core)
6. `indexer_svc/app/main.py`, `embedder.py`, `store.py` (vector indexing)
7. `postgres_server/init/01_documents.sql` and `02_chunks.sql` (schema truth)


## 14) One-paragraph mental model

P2M is a staged document-processing platform where OCR and NLP services convert PDFs into structured, translated semantic chunks, and an indexer stores hybrid vectors (dense + sparse) in pgvector for retrieval. In parallel, an API plus RabbitMQ ingestion path manages upload lifecycle and document status tracking. The repository is partially transitioning from local file-event orchestration to queue-first microservice orchestration, so both modes coexist and must be interpreted intentionally when extending or debugging the system.
