# P2M System Architecture (Updated)

This document describes the current architecture across ingestion, OCR/NLP/indexing, RAG chat, and conversation storage.

---

## 1. High-Level Components

```
                                ┌──────────────────────────────┐
                                │      Frontend (React)        │
                                │  Upload + Chat UI (Vite)     │
                                └──────────────┬───────────────┘
                                               │
                 HTTP /upload                  │ WebSocket /rag/ws
                                               │
                            ┌──────────────────▼──────────────────┐
                            │       FastAPI Upload API (app)      │
                            │            port 8000                │
                            └──────────────┬───────────┬──────────┘
                                           │           │
                                           │           │
                                  ┌────────▼───┐   ┌──▼──────────────┐
                                  │   MinIO    │   │   PostgreSQL     │
                                  │ PDF object │   │ documents/chunks │
                                  │  storage   │   │ + chat_history   │
                                  └────────────┘   └────────┬─────────┘
                                                             │
                                                             │ read/write
                           ┌─────────────────────────────────▼────────────────────────────────┐
                           │                  RAG Service (FastAPI, port 8001)              │
                           │  retrieve (pgvector + BM25) + generate (Ollama) + memory save  │
                           └─────────────────────────────────┬────────────────────────────────┘
                                                             │
                                                             ▼
                                                         Ollama LLM


Async processing path (queue-based):

FastAPI -> RabbitMQ ocr_queue -> OCR -> RabbitMQ nlp_queue -> NLP -> RabbitMQ indexer_queue -> Indexer -> PostgreSQL chunks

Synchronous processing path (default in app/api.py):

FastAPI background task -> run_pipeline.py -> OCR -> NLP -> Indexer -> PostgreSQL chunks
```

---

## 2. Services And Responsibilities

| Service | Role | Main Files |
|---|---|---|
| Frontend | Upload PDF and run chat UI | `front-end/src/app/components/AIAgentSpace.tsx` |
| Upload API | Accept PDF uploads, persist metadata, trigger pipeline | `app/api.py` |
| OCR | Extract structured blocks/pages from PDF | `ocr_service/main.py`, `ocr_service/consumer.py` |
| NLP Pipeline | Clean, detect language, translate, chunk | `nlp_pipeline_svc/app/pipeline.py`, `nlp_pipeline_svc/consumer.py` |
| Indexer | Build embeddings and upsert vectors to pgvector | `indexer_svc/app/embedder.py`, `indexer_svc/app/store.py`, `indexer_svc/consumer.py` |
| RAG Service | Retrieve chunks + stream answer tokens via WebSocket | `rag_service/start_rag.py`, `rag_service/retriever.py`, `rag_service/pipeline.py` |
| Chat Storage | Persist per-session chat turns in PostgreSQL table | `rag_service/memory.py`, `app/models.py` |
| RabbitMQ | Queue transport (ocr_queue, nlp_queue, indexer_queue + DLQ) | `rabbitmq_server/docker-compose.yml` |
| MinIO | PDF object storage bucket | `minio_server/docker-compose.yml` |
| PostgreSQL + pgvector | Document metadata, vector chunks, chat history | `postgres_server/docker-compose.yml`, `app/models.py` |
| Redis | Infra service present (cache/session candidate) | `redis_server/docker-compose.yml` |

---

## 3. Processing Modes In Repository

The repository currently contains multiple valid processing paths.

### A. Background Local Pipeline (Current API default)

`PIPELINE_TRIGGER_MODE=run_pipeline` in `app/api.py` triggers:

1. Upload API stores PDF in MinIO and creates document row.
2. API marks document as processing.
3. Background task downloads PDF and runs `run_pipeline.py`.
4. `run_pipeline.py` executes OCR -> NLP -> Indexer sequentially.
5. Chunks are stored in PostgreSQL/pgvector; document status updated.

Key files:
- `app/api.py`
- `run_pipeline.py`
- `ocr_service/main.py`
- `nlp_pipeline_svc/app/main.py`
- `indexer_svc/app/main.py`

### B. Legacy RabbitMQ Path (Still available)

`PIPELINE_TRIGGER_MODE != run_pipeline` in `app/api.py` currently uses:

1. API publishes `{doc_id, url, source}` to `ocr_queue`.
2. `rabbitmq_server/consumers/ocr_services.py` consumes message.
3. Consumer runs OCR -> NLP -> Indexer and updates DB.

Key files:
- `rabbitmq_server/Producers/ingestion.py`
- `rabbitmq_server/consumers/ocr_services.py`

### C. Full Microservice Queue Chain (Service modules present)

Service-specific consumers/publishers implement a staged queue pipeline:

1. OCR consumer reads `ocr_queue` and publishes to `nlp_queue`.
2. NLP consumer reads `nlp_queue` and publishes to `indexer_queue`.
3. Indexer consumer reads `indexer_queue` and finalizes indexing.

Key files:
- `ocr_service/consumer.py`, `ocr_service/publisher.py`
- `nlp_pipeline_svc/consumer.py`, `nlp_pipeline_svc/publisher.py`
- `indexer_svc/consumer.py`

---

## 4. End-To-End Data Flows

### 4.1 Upload And Indexing Flow

```
Client -> POST /upload -> Upload API
Upload API -> MinIO (store PDF)
Upload API -> PostgreSQL documents (create row)

Then one of:

(A) background run_pipeline
    -> OCR -> NLP -> Indexer -> PostgreSQL chunks

(B) RabbitMQ
    -> ocr_queue -> OCR/NLP/Indexer consumers -> PostgreSQL chunks
```

### 4.2 RAG Chat Flow

```
Client -> WebSocket ws://localhost:8001/rag/ws
RAG Service -> retrieve chunks from PostgreSQL (hybrid: vector + BM25)
RAG Service -> generate answer stream from Ollama
RAG Service -> save turn history in PostgreSQL chat_history
RAG Service -> stream token events back to client
```

---

## 5. Queue Contracts (Staged Pipeline)

### 5.1 OCR Queue (ingestion)

Legacy payload (`rabbitmq_server/Producers/ingestion.py`):

```json
{
  "doc_id": "uuid-string",
  "url": "http://localhost:9000/pdf-storage/<file>.pdf",
  "source": "user_upload"
}
```

### 5.2 NLP Queue (from OCR service publisher)

```json
{
  "document_id": "uuid-string",
  "tenant_id": "tenant-id",
  "filename": "document.pdf",
  "pages": [],
  "metadata": {},
  "retry_count": 0
}
```

### 5.3 Indexer Queue (from NLP service publisher)

```json
{
  "document_id": "uuid-string",
  "tenant_id": "tenant-id",
  "filename": "document.pdf",
  "chunks": [],
  "metadata": {},
  "retry_count": 0
}
```

---

## 6. Storage Model

### 6.1 PostgreSQL Core Tables

- `documents`: upload metadata + status + metadata payload.
- `chunks`: vectorized chunks (`dense_vec`, `sparse_vec`) for retrieval.
- `chat_history`: conversation memory by `session_id` (JSONB messages).

### 6.2 Chat Storage

Chat memory is currently stored in PostgreSQL via `PostgresChatMessageHistory`.

Source:
- `rag_service/memory.py` (table creation + save/load/clear)
- `rag_service/config.py` (`MEMORY_TABLE_NAME`, `MEMORY_MAX_EXCHANGES`)

### 6.3 Redis Status

Redis container exists in `redis_server/docker-compose.yml`.
At present, repository runtime wiring for chat memory uses PostgreSQL; Redis is available as infrastructure for future cache/session usage.

---

## 7. Status Progression

Document status/pipeline values observed in code paths include:

- Upload/API states: `uploaded`, `processing`, `completed`, `failed`.
- Pipeline sub-states (queue services): `ocr_processing`, `ocr_done`, `ocr_failed`, `nlp_processing`, `nlp_done`, `nlp_failed`, `indexing`, `indexed`, `index_failed`.

---

## 8. Runtime Ports And Endpoints

| Service | Port | Endpoint / Usage |
|---|---:|---|
| Frontend (Vite) | 5173 (typical dev) | http://localhost:5173 |
| Upload API (FastAPI) | 8000 | http://localhost:8000, `/upload`, `/docs` |
| RAG Service (FastAPI WS) | 8001 | ws://localhost:8001/rag/ws, `/health`, `/health/model` |
| PostgreSQL | 5432 | postgresql://localhost:5432 |
| MinIO API | 9000 | http://localhost:9000 |
| MinIO Console | 9001 | http://localhost:9001 |
| RabbitMQ AMQP | 5672 | amqp://localhost |
| RabbitMQ UI | 15672 | http://localhost:15672 |
| Redis | 6379 | redis://localhost:6379 |
| Ollama | 11434 | http://localhost:11434 |

---

## 9. Key Integration Points

1. Upload trigger and mode switch
   - `app/api.py`
   - Controls `PIPELINE_TRIGGER_MODE` and starts either background local pipeline or RabbitMQ trigger.

2. Legacy queue producer and consumer
   - `rabbitmq_server/Producers/ingestion.py`
   - `rabbitmq_server/consumers/ocr_services.py`

3. Staged queue microservices
   - `ocr_service/consumer.py`
   - `nlp_pipeline_svc/consumer.py`
   - `indexer_svc/consumer.py`

4. RAG retrieval and chat streaming
   - `rag_service/start_rag.py`
   - `rag_service/retriever.py`
   - `rag_service/pipeline.py`
   - `rag_service/websocket_handler.py`

5. Chat persistence
   - `rag_service/memory.py`
   - `app/models.py` (`ChatHistory`)

---

## 10. Health And Verification Checklist

1. Infrastructure up
   - PostgreSQL, MinIO, RabbitMQ, Redis containers are running.

2. Upload API available
   - `GET http://localhost:8000/docs` loads.

3. RAG service available
   - `GET http://localhost:8001/health` returns ok.
   - WebSocket connection to `/rag/ws` returns `ready` event.

4. Indexing data exists
   - `chunks` table has rows for uploaded docs.

5. Chat memory persists
   - `chat_history` table receives user/assistant messages.

---

## 11. Notes For Ongoing Integration

- The repository contains both legacy and new queue integration patterns.
- Keep API producer payload and consumer payload aligned when selecting queue mode.
- If Redis is adopted for chat memory or caching, document the new storage path and TTL policy in this file.
