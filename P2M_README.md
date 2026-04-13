# P2M — Document Processing & RAG Platform
## Complete Setup & Launch Guide

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Project Structure](#2-project-structure)
3. [Environment Setup](#3-environment-setup)
4. [Python Virtual Environment](#4-python-virtual-environment)
5. [Frontend Installation](#5-frontend-installation)
6. [Environment Variables (.env)](#6-environment-variables-env)
7. [Docker Infrastructure Services](#7-docker-infrastructure-services)
8. [Database Migration](#8-database-migration)
9. [Ollama — Local LLM](#9-ollama--local-llm)
10. [Starting All Services](#10-starting-all-services)
11. [Full Pipeline Workflow](#11-full-pipeline-workflow)
12. [Service URLs Reference](#12-service-urls-reference)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. System Requirements

Before starting, ensure the following are installed on your machine:

| Tool | Version | Purpose |
|------|---------|---------|
| **Docker Desktop** | Latest | PostgreSQL, MinIO, RabbitMQ, Redis |
| **Python** | 3.10+ | All backend services |
| **Node.js** | 18+ | React frontend |
| **Git** | Any | Clone the repository |
| **Ollama** | Latest | Local LLM (qwen2.5:7b for metadata + llama3 for RAG) |
| **CUDA** (optional) | 12.x | GPU acceleration for embeddings |

> ⚠️ **Windows users**: All commands below use PowerShell. Run as a standard user (not Administrator).

---

## 2. Project Structure

```
P2M/
├── app/                        # Ingestion API (FastAPI) — upload endpoint
│   ├── api.py                  # REST endpoints
│   ├── config.py               # App settings + RabbitMQ config
│   ├── database.py             # SQLAlchemy DB connection
│   ├── models.py               # ORM models
│   ├── publisher.py            # RabbitMQ publisher → OCR queue
│   └── start_api.py            # Entry point (port 8000)
│
├── ocr_service/                # OCR microservice
│   ├── main.py                 # run(pdf_path) — API + local fallback
│   ├── paddle_ocr.py           # PaddleOCR VL (cloud API + local model)
│   │                           # API path uses parsing_res_list directly
│   │                           # Both paths share _build_blocks_from_res()
│   ├── pdf_to_images.py        # PDF → page images (local fallback only)
│   ├── config.py               # ALLOWED_LABELS, LABEL_MAP, NLP_IGNORED_LABELS
│   ├── output_writer.py        # Builds OcrDocument and publishes event
│   ├── consumer.py             # RabbitMQ consumer ← ocr_queue
│   └── publisher.py            # RabbitMQ publisher → nlp_queue
│
├── nlp_pipeline_svc/           # NLP microservice
│   ├── app/
│   │   ├── pipeline.py         # NlpOrchestrator — global block index,
│   │   │                       # per-block chunking, metadata promotion
│   │   ├── config.py           # NLP settings + RabbitMQ config
│   │   └── nlp/
│   │       ├── language_detection.py  # lingua-py, returns list[str]
│   │       │                          # Detects: ar | fr | en | mixed
│   │       ├── translation.py         # Helsinki-NLP opus-mt models
│   │       │                          # Handles mixed-language blocks
│   │       ├── metadata_extractor.py  # Two-stage: regex + qwen2.5:7b (Ollama)
│   │       │                          # Fields: title, nit_number, organization,
│   │       │                          #         client, location, deadline,
│   │       │                          #         budget, contact_email, contact_phone
│   │       ├── chunker.py             # Block-type-aware semantic chunking
│   │       └── cleaning.py            # Text normalisation
│   ├── consumer.py             # RabbitMQ consumer ← nlp_queue
│   └── publisher.py            # RabbitMQ publisher → indexer_queue
│
├── indexer_svc/                # Indexer microservice (embeddings + pgvector)
│   ├── app/
│   │   ├── embedder.py         # BAAI/bge-m3 — dense + sparse embeddings
│   │   ├── store.py            # pgvector upsert (chunks table)
│   │   └── config.py           # Indexer settings + RabbitMQ config
│   └── consumer.py             # RabbitMQ consumer ← indexer_queue
│
├── rag_service/                # RAG microservice (retrieval + generation)
│   ├── config.py               # RAG settings
│   ├── models.py               # WebSocket message schemas
│   ├── retriever.py            # Hybrid search: pgvector <#> + BM25 → RRF
│   ├── generator.py            # Ollama llama3 streaming client
│   ├── pipeline.py             # Orchestrator: retrieve → prompt → stream
│   ├── websocket_handler.py    # WebSocket session management
│   └── start_rag.py            # Entry point (port 8001)
│
├── front-end/                  # React + Vite UI
│   └── src/app/components/
│       └── AIAgentSpace.tsx    # Upload + RAG chat interface
│
├── shared/                     # Shared Pydantic models and event bus
│   ├── models.py               # OcrBlock, OcrPage, OcrDocument
│   │                           # NlpChunk, NlpDocument
│   │                           # doc_metadata placed before chunks in output
│   └── event_bus.py            # Disk-based event passing (legacy)
│
├── postgres_server/            # PostgreSQL + pgvector (Docker)
├── minio_server/               # MinIO object storage (Docker)
├── rabbitmq_server/            # RabbitMQ message broker (Docker)
├── redis_server/               # Redis cache (Docker)
│
└── .env                        # All secrets and config (create from this guide)
```

---

## 3. Environment Setup

### Clone the repository

```powershell
git clone <repository_url> P2M
cd P2M
```

---

## 4. Python Virtual Environment

```powershell
# Create virtual environment
python -m venv .venv

# Activate (Windows PowerShell)
.venv\Scripts\activate

# Install all Python dependencies
pip install -r requirements.txt
```

### Core NLP dependencies

```powershell
# Language detection (replaces langdetect)
pip install lingua-language-detector

# Translation tokenizer support
pip install sentencepiece

# Translation + embeddings backend
pip install transformers

# Metadata extraction LLM client (uses Ollama via requests — no extra install)
# requests is already in requirements.txt
```

### Install FlagEmbedding (required for BAAI/bge-m3)

```powershell
pip install FlagEmbedding
```

### Install PyTorch with CUDA support

> ⚠️ The embedding model requires PyTorch 2.6+. Install with CUDA 12.4 (compatible with CUDA 12.x on your machine):

```powershell
pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
```

Verify:
```powershell
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
# Expected: 2.6.0+cu124 / True
```

> ⚠️ **CPU-only machines**: Install the lighter build instead:
> ```powershell
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> ```

### Install RAG service dependencies

```powershell
pip install fastapi uvicorn[standard] asyncpg httpx pydantic pydantic-settings websockets aio_pika
```

---

## 5. Frontend Installation

```powershell
cd front-end
npm install
cd ..
```

---

## 6. Environment Variables (.env)

Create a `.env` file at the **project root** (`C:\P2M\.env`) with the following content:

```env
# ── PostgreSQL ────────────────────────────────────────────────────────────────
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=123456789

# ── MinIO (Object Storage) ────────────────────────────────────────────────────
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=pdf-storage
MINIO_SECURE=false

# ── RabbitMQ (Message Broker) ─────────────────────────────────────────────────
# Must match RABBITMQ_DEFAULT_USER and RABBITMQ_DEFAULT_PASS in rabbitmq_server/docker-compose.yml
RABBITMQ_URL=amqp://admin:secretpassword@localhost/
EVENT_EXCHANGE=p2m_events
OCR_QUEUE=ocr_queue
NLP_QUEUE=nlp_queue
INDEXER_QUEUE=indexer_queue
MAX_RETRY=3
MAX_WORKERS=2

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379

# ── OCR Service ───────────────────────────────────────────────────────────────
PADDLE_API_URL=https://a4beybi7x2z4r2p6.aistudio-app.com/layout-parsing
PADDLE_API_TOKEN=your_token_here
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
OCR_TIMEOUT=300

# ── NLP Service ───────────────────────────────────────────────────────────────
NLP_TARGET_LANG=en
NLP_TIMEOUT=300

# ── Indexer Service ───────────────────────────────────────────────────────────
EMBEDDING_MODEL=BAAI/bge-m3
EMBED_BATCH_SIZE=16
INDEXER_TIMEOUT=600

# ── RAG Service ───────────────────────────────────────────────────────────────
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3                     # used for RAG answer generation

# ── Pipeline Mode ─────────────────────────────────────────────────────────────
# Options: "rabbitmq" (async queues) or "run_pipeline" (synchronous local)
PIPELINE_TRIGGER_MODE=rabbitmq

# ── API ───────────────────────────────────────────────────────────────────────
API_PORT=8000
```

> ⚠️ **Important**: Match `RABBITMQ_URL` credentials exactly with what is set in `rabbitmq_server/docker-compose.yml` under `RABBITMQ_DEFAULT_USER` and `RABBITMQ_DEFAULT_PASS`.

---

## 7. Docker Infrastructure Services

Make sure **Docker Desktop is running**, then start each service:

```powershell
# MinIO — Object Storage (ports 9000, 9001)
cd minio_server
docker-compose up -d
cd ..

# PostgreSQL + pgvector — Database (port 5432)
cd postgres_server
docker-compose up -d
cd ..

# RabbitMQ — Message Broker (ports 5672, 15672)
cd rabbitmq_server
docker-compose up -d
cd ..

# Redis — Cache (port 6379)
cd redis_server
docker-compose up -d
cd ..
```

Verify all containers are running:
```powershell
docker ps
```

You should see 4 containers: `postgres`, `minio`, `rabbitmq`, `redis`.

### Verify RabbitMQ

Open `http://localhost:15672` in your browser.
Login with the credentials from your `docker-compose.yml` (default: `admin` / `secretpassword`).

### Verify MinIO

Open `http://localhost:9001` in your browser.
Login: `minioadmin` / `minioadmin` (or your configured values).
Create a bucket named `pdf-storage` if it does not exist.

---

## 8. Database Migration

Run Alembic migrations to create all required tables:

```powershell
# Activate virtual environment first
.venv\Scripts\activate

cd app
alembic upgrade head
cd ..
```

This creates the `documents` table and other required schemas.

The `chunks` table with pgvector support is created automatically when the Indexer service connects for the first time (via `store.py → _ensure_schema()`).

---

## 9. Ollama — Local LLM

Install Ollama from [https://ollama.com](https://ollama.com), then pull both required models:

```powershell
# RAG answer generation (~4.7 GB)
ollama pull llama3

# Metadata extraction — title, organization, client, location
# Better multilingual support: Arabic, French, English (~4.7 GB)
ollama pull qwen2.5:7b

# Verify both are available
ollama list
```

> **Why two models?**
> - `llama3` — used by the RAG service for streaming answer generation
> - `qwen2.5:7b` — used by the NLP metadata extractor; better Arabic and French support, more reliable JSON output

---

## 10. Starting All Services

Open **7 separate PowerShell terminals**, activate the virtual environment in each Python terminal, and start the services in order.

### Terminal 1 — Ollama (LLM server)

```powershell
ollama serve
```

> Keep running in background. Should print: `Listening on 127.0.0.1:11434`

---

### Terminal 2 — Backend API (Ingestion, port 8000)

```powershell
cd C:\P2M
.venv\Scripts\activate
python app/start_api.py
```

> Expected: `Uvicorn running on http://0.0.0.0:8000`

---

### Terminal 3 — RAG Service (WebSocket, port 8001)

```powershell
cd C:\P2M
.venv\Scripts\activate
python rag_service/start_rag.py
```

> Expected: `✅ RAG service ready | WS endpoint: ws://0.0.0.0:8001/rag/ws`

---

### Terminal 4 — OCR Consumer (RabbitMQ)

```powershell
cd C:\P2M
.venv\Scripts\activate
python -c "
import asyncio
from ocr_service.consumer import OCRConsumer

async def main():
    consumer = OCRConsumer(db_pool=None, minio_client=None)
    await consumer.start()
    print('OCR Consumer running...')
    await asyncio.Future()

asyncio.run(main())
"
```

> Expected: `OCR Consumer running...`

---

### Terminal 5 — NLP Consumer (RabbitMQ)

```powershell
cd C:\P2M
.venv\Scripts\activate
python -c "
import asyncio
from nlp_pipeline_svc.consumer import NLPConsumer

async def main():
    consumer = NLPConsumer(db_pool=None)
    await consumer.start()
    print('NLP Consumer running...')
    await asyncio.Future()

asyncio.run(main())
"
```

> Expected: `NLP Consumer running...`

---

### Terminal 6 — Indexer Consumer (RabbitMQ)

```powershell
cd C:\P2M
.venv\Scripts\activate
python -c "
import asyncio
from indexer_svc.consumer import IndexerConsumer

async def main():
    consumer = IndexerConsumer(db_pool=None)
    await consumer.start()
    print('Indexer Consumer running...')
    await asyncio.Future()

asyncio.run(main())
"
```

> Expected: `Indexer Consumer running...`

---

### Terminal 7 — Frontend (React + Vite, port 5173)

```powershell
cd C:\P2M\front-end
npm run dev
```

> Expected: `VITE ready on http://localhost:5173`

---

## 11. Full Pipeline Workflow

Once all 7 services are running:

```
1. Open http://localhost:5173 in your browser
2. Drag and drop a PDF into the upload zone
3. The pipeline runs automatically:

   Upload PDF
       ↓
   app/api.py              → stores in MinIO + PostgreSQL
       ↓ publishes to [ocr_queue]
   ocr_service             → PaddleOCR VL cloud API (parsing_res_list)
                           → local PaddleOCRVL model (fallback)
                           → all text labels kept (header, footer, footnote…)
                           → DB status: ocr_processing → ocr_done
       ↓ publishes to [nlp_queue]
   nlp_pipeline_svc        → metadata extraction (regex + qwen2.5:7b)
                           →   title, nit_number, organization, client,
                           →   location, deadline, budget, contacts
                           → language detection (lingua-py: ar | fr | en | mixed)
                           → translation to English (Helsinki-NLP opus-mt)
                           → semantic chunking (sentence-transformers)
                           → DB status: nlp_processing → nlp_done
       ↓ publishes to [indexer_queue]
   indexer_svc             → BAAI/bge-m3 embeddings → pgvector
                           → DB status: indexing → indexed ✅

4. Once indexed, type a question in the chat
5. RAG service retrieves relevant chunks (hybrid BM25 + semantic)
6. llama3 generates a streaming answer
7. Answer streams token-by-token into the chat UI with source citations
```

### NLP output format

The NLP service produces a structured JSON document. Document-level metadata appears **before** the chunks:

```json
{
  "doc_id": "tender.pdf",
  "source_lang": "fr",
  "doc_metadata": {
    "title": "Construction of Block Primary Health Unit",
    "nit_number": "PCO/BBSR/953/144",
    "organization": "Engineering Projects (India) Ltd.",
    "client": "National Health Mission, Govt. of Odisha",
    "location": "Lahunipada, Sundergarh District, Odisha",
    "deadline": "2023-12-19",
    "budget": "Rs. 54,53,776/-",
    "contact_email": "dheeranjan.m@engineeringprojects.com",
    "contact_phone": null
  },
  "chunks": [
    {
      "chunk_id": "a9c014...",
      "page_index": 0,
      "block_index": 0,
      "chunk_index": 0,
      "block_type": "paragraph_title",
      "source_lang": "en",
      "text_original": "NOTICE INVITING e-TENDER (NIT)",
      "text_en": "NOTICE INVITING e-TENDER (NIT)",
      "metadata": {
        "section_title": null,
        "context": null,
        "translation_failed": false
      }
    }
  ]
}
```

### Language support

| Language | OCR | Detection | Translation | Metadata extraction |
|----------|-----|-----------|-------------|-------------------|
| English  | ✅  | ✅ lingua | passthrough | ✅ qwen2.5:7b |
| French   | ✅  | ✅ lingua | ✅ opus-mt-fr-en | ✅ qwen2.5:7b |
| Arabic   | ✅  | ✅ lingua | ✅ opus-mt-ar-en | ✅ qwen2.5:7b |
| Mixed (ar+fr) | ✅ | ✅ per segment | ✅ per segment | ✅ |

### Monitor pipeline status in PostgreSQL

```sql
SELECT id, filename, pipeline_status, error_message, created_at
FROM documents
ORDER BY created_at DESC
LIMIT 10;
```

Expected status progression:
```
uploaded → ocr_processing → ocr_done → nlp_processing → nlp_done → indexing → indexed
```

### Monitor RabbitMQ queues

Open `http://localhost:15672` → **Queues** tab.

You should see messages flow through:
- `ocr_queue` → `nlp_queue` → `indexer_queue`

---

## 12. Service URLs Reference

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | http://localhost:5173 | Main UI (upload + chat) |
| Backend API | http://localhost:8000 | Document upload endpoint |
| API Docs | http://localhost:8000/docs | Swagger UI |
| RAG WebSocket | ws://localhost:8001/rag/ws | Streaming RAG endpoint |
| RAG Health | http://localhost:8001/health | Liveness check |
| RAG Model Health | http://localhost:8001/health/model | Ollama model check |
| RabbitMQ UI | http://localhost:15672 | Queue monitoring |
| MinIO UI | http://localhost:9001 | Object storage browser |
| Ollama | http://localhost:11434 | LLM inference server |
| PostgreSQL | localhost:5432 | Database |
| Redis | localhost:6379 | Cache |

---

## 13. Troubleshooting

### RabbitMQ: `ProbableAuthenticationError`

Your credentials don't match. Check `rabbitmq_server/docker-compose.yml`:
```yaml
environment:
  - RABBITMQ_DEFAULT_USER=admin
  - RABBITMQ_DEFAULT_PASS=secretpassword
```
Then update `.env`:
```env
RABBITMQ_URL=amqp://admin:secretpassword@localhost/
```

---

### RabbitMQ: `PRECONDITION_FAILED — inequivalent arg`

A queue was previously declared with different arguments. Delete it:
1. Open `http://localhost:15672` → **Queues** tab
2. Click the queue name → scroll down → **Delete**
3. Restart the affected consumer

---

### OCR: API returns 401 Unauthorized

Your token is missing or expired. Check `ocr_service/paddle_ocr.py`:
```python
API_TOKEN = os.environ.get("PADDLE_API_TOKEN", "your_token_here")
```
Get a fresh token from [https://aistudio.baidu.com/account/accessToken](https://aistudio.baidu.com/account/accessToken).

Test the token:
```powershell
curl.exe -I https://a4beybi7x2z4r2p6.aistudio-app.com/layout-parsing `
  -H "Authorization: token your_token_here"
# Expected: HTTP/1.1 400 (not 401) means token is valid
```

---

### OCR: API returns 500 / app is down

The AIStudio hosted app may have stopped (free-tier apps sleep after inactivity). To restart:
1. Go to [https://aistudio.baidu.com](https://aistudio.baidu.com)
2. Navigate to your deployed app and click **Start**
3. Wait ~2 minutes for the model to load

The pipeline falls back to the local PaddleOCRVL model automatically. To force local mode, blank the API URL in `.env`:
```env
PADDLE_API_URL=
PADDLE_API_TOKEN=
```

---

### OCR: Local model crashes with cuDNN DLL error

```
OSError: [WinError 127] cudnn_cnn64_9.dll not found
```

Install the CPU-only build of PyTorch (removes the nvidia CUDA packages):
```powershell
pip uninstall nvidia-cudnn-cu11 -y
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

---

### NLP: `cannot import name 'detect_languages'`

The `language_detection.py` file contains wrong content (translation.py was pasted into it). Overwrite it:
```powershell
# Verify what's in the file
Get-Content C:\P2M\nlp_pipeline_svc\app\nlp\language_detection.py | Select-Object -First 5
# Should start with: """P2M/nlp_pipeline_svc/app/nlp/language_detection.py
# If it starts with: """P2M/nlp_service/translation.py — the file is wrong
```

---

### NLP: `lingua-language-detector not installed`

```powershell
pip install lingua-language-detector
```

---

### NLP: Metadata extraction returns all null fields

Make sure Ollama is running and `qwen2.5:7b` is pulled:
```powershell
ollama serve          # in a separate terminal if not running
ollama pull qwen2.5:7b
ollama list           # should show qwen2.5:7b
```

Verify Ollama is reachable:
```powershell
curl.exe http://localhost:11434/api/tags
```

---

### NLP: Translation model not loading

Helsinki-NLP models are downloaded from HuggingFace on first use (~300 MB each). If your server has no internet:
```powershell
$env:TRANSFORMERS_OFFLINE = "1"
$env:HF_HUB_OFFLINE = "1"
```
Pre-download the models on a machine with internet access first:
```python
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-fr-en")
AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-ar-en")
```

---

### Embedder: `ValueError: torch.load requires torch >= 2.6`

```powershell
pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
```

---

### Database: Table does not exist

Run migrations:
```powershell
cd app
alembic upgrade head
cd ..
```

---

### RAG: `column "metadata" does not exist`

This means the retriever is using an old config. Verify `rag_service/config.py` has:
```python
CHUNKS_TABLE        = "chunks"
CHUNK_ID_COL        = "chunk_id"
CHUNK_TEXT_COL      = "text_en"
CHUNK_EMBEDDING_COL = "dense_vec"
EMBEDDING_DIM       = 1024
```
There should be **no** `CHUNK_METADATA_COL` setting.

---

### RAG: `Cannot connect to Ollama`

Make sure Ollama is running:
```powershell
ollama serve
```
And the model is pulled:
```powershell
ollama list
# Should show: llama3, qwen2.5:7b
```

---

### chunks table: `document_id` is NULL

If you uploaded a document before the indexer assigned the UUID link, update manually:
```sql
UPDATE chunks
SET document_id = '<your-document-uuid>'
WHERE doc_id = 'your_filename.pdf'
  AND document_id IS NULL;
```
Get the UUID from:
```sql
SELECT id, filename FROM documents ORDER BY created_at DESC LIMIT 5;
```

---

### Frontend: Chat input disabled / "En attente d'un document"

The chat only activates after a successful upload that returns a `document_id`. Check:
1. Backend API is running on port 8000
2. Upload response contains `id`, `documentId`, or `document_id`
3. Browser console for network errors

---

*Happy Parsing! 🚀*
