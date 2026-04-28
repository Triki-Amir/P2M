# P2M - Document Processing & RAG Platform

## 1. Architecture Overview
P2M is a microservices-based Document Processing and Retrieval-Augmented Generation (RAG) platform. The system follows an event-driven architecture utilizing RabbitMQ as the central message broker, PostgreSQL (with pgvector) for relational data and embeddings, MinIO for S3-compatible document storage, and Redis for caching and chat history management.

**Core Data Flow:**
1. **Ingestion**: A user uploads a document through the Frontend/API. The document is saved to MinIO, and a metadata record is created in PostgreSQL. An `ocr_task` event is published to RabbitMQ.
2. **OCR & Extraction**: The OCR microservice picks up the message, downloads the document from MinIO, extracts text/images using local models or the PaddleOCR API, and publishes an `nlp_task` event.
3. **NLP Structuring**: The NLP microservice processes the raw text, cleans it, segments it, and publishes an `indexer_task` event.
4. **Indexing**: The Indexer microservice receives the cleaned chunks, interacts with an embedding model to generate vector embeddings, and stores these into the Postgres `pgvector` tables.
5. **RAG & Chat**: The RAG service retrieves matching context from PostgreSQL via vector similarity search and streams answers to the client using WebSockets.

---

## 2. Services: Roles and Details

| Service | Role & Responsibility | Tech Stack | Port |
| :--- | :--- | :--- | :--- |
| **Frontend** | User Interface for uploading documents and chatting with the AI. | React, Vite, TailwindCSS | `5173` |
| **Ingestion API**| Entry point for file uploads, DB metadata creation, and triggering the pipeline. | Python, FastAPI, SQLAlchemy | `8000` |
| **OCR Service** | Asynchronous worker that performs Optical Character Recognition on uploaded documents. | Python, PaddleOCR | N/A |
| **NLP Service** | Asynchronous worker that processes OCR output text, structures, and cleans it. | Python, Spacy/NLTK | N/A |
| **Indexer Service**| Asynchronous worker that chunks and embeds text, pushing to pgvector database. | Python, LangChain, HuggingFace | N/A |
| **RAG Service** | WebSocket API providing context-aware answers to user queries. | Python, FastAPI WS, Ollama | `8001` |
| **Infrastructure** | Database (`5432`), RabbitMQ (`5672`), MinIO (`9000`/`9001`), Redis (`6379`) | Docker | Various |

---

## 3. How to Run It From Scratch

You will need Docker Desktop, Python 3.10+, Node 18+, and Ollama installed. Open **separate terminals** for each of the following components to run them concurrently.

### Terminal 1: Infrastructure
```bash
docker-compose -f postgres_server/docker-compose.yml up -d
docker-compose -f minio_server/docker-compose.yml up -d
docker-compose -f rabbitmq_server/docker-compose.yml up -d
docker-compose -f redis_server/docker-compose.yml up -d
```

### Terminal 2: Ingestion Service (API)
```powershell
.\.venv\Scripts\Activate.ps1
cd ingestion_service
python start_api.py
```

### Terminal 3: OCR Service
```powershell
.\.venv\Scripts\Activate.ps1
python -m ocr_service.consumer
```

### Terminal 4: NLP Pipeline Service
```powershell
.\.venv\Scripts\Activate.ps1
python -m nlp_pipeline_svc.consumer
```

### Terminal 5: Indexer Service
```powershell
.\.venv\Scripts\Activate.ps1
python -m indexer_svc.consumer
```

### Terminal 6: RAG Service (Chat WebSocket)
```powershell
.\.venv\Scripts\Activate.ps1
cd rag_service
python start_rag.py
```

### Terminal 7: Frontend Application
```powershell
cd front-end
npm install
npm run dev
```

### Terminal 8: Compliance Service (Optional)
```powershell
.\.venv\Scripts\Activate.ps1
python -m compliance_service.consumer
```

---

## 4. Project Skeleton

```text
P2M/
+-- .env                       # Root environment parameters
+-- README.md                  # Main Architecture and Setup Guide (This file)
+-- app/                       # Shared modules and models
+-- front-end/                 # React UI application
+-- ingestion_service/         # REST API for File Upload & Metadata
+-- ocr_service/               # OCR microservice worker
+-- nlp_pipeline_svc/          # Text structuring microservice worker
+-- indexer_svc/               # Embedding microservice worker
+-- rag_service/               # RAG Query & WebSocket server
+-- compliance_service/        # Regulatory check service
+-- postgres_server/           # PostgreSQL / pgvector config
+-- minio_server/              # MinIO config
+-- rabbitmq_server/           # RabbitMQ config
+-- redis_server/              # Redis config
```
