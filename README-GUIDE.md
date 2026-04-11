# P2M Document Processing Pipeline

This repository provides an automated document analysis pipeline to extract, process, and index PDF documents (specifically tenders) into a searchable knowledge base using AI (OCR, NLP, Indexer).

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Project Setup](#project-setup)
3. [Running Infrastructure Services](#running-infrastructure-services)
4. [Starting the Application](#starting-the-application)
    - [1. Backend API (Uploader)](#1-backend-api-uploader)
    - [2. Frontend (React/Vite)](#2-frontend-reactvite)
    - [3. Background Services (RabbitMQ Consumers)](#3-background-services-rabbitmq-consumers)
5. [Pipeline Workflow Details](#pipeline-workflow-details)
6. [Troubleshooting & Tips](#troubleshooting--tips)

---

## Prerequisites

Before starting, ensure you have the following installed on your machine:
- **Docker and Docker Compose** (crucial for PostgreSQL, MinIO, RabbitMQ, and Redis instances)
- **Node.js** (v18+ recommended) for the frontend
- **Python 3.10+** for the machine learning pipelines and FastAPI
- **Git**

## Project Setup

1. **Clone the Repository** and open it in your editor:
   ```bash
   git clone <repository_url> P2M
   cd P2M
   ```

2. **Set up Python Virtual Environment**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/Mac:
   source .venv/bin/activate
   
   # Install dependencies
   pip install -r requirements.txt
   ```

3. **Set up Node Modules for Frontend**:
   ```bash
   cd front-end
   npm install
   cd ..
   ```

4. **Environment Variables**:
   Copy the example environment files (`.env.example`) to `.env` where necessary, specifically in the project root and in `minio_server/minio-backend/` if required.

## Running Infrastructure Services

The application relies on several containerized services. Start them securely using Docker Compose. Make sure Docker Desktop is running before executing these commands.

Open a new terminal at the root directory of the project, then run the following to start MinIO, PostgreSQL, RabbitMQ, and Redis:

```bash
# Start MinIO (Object Storage)
cd minio_server
docker-compose up -d
cd ..

# Start PostgreSQL (Database)
cd postgres_server
docker-compose up -d
cd ..

# Start RabbitMQ (Message Broker)
cd rabbitmq_server
docker-compose up -d
cd ..

# Start Redis (Caching/Session)
cd redis_server
docker-compose up -d
cd ..
```

Wait a moment for PostgreSQL and other services to fully initialize.

## Starting the Application

With your infrastructure containers fully running, you need to execute three different processes to get the full application operational:

### 1. Backend API (Uploader and Database Handler)
Open a new terminal, activate your virtual environment, and start the FastAPI service:
```bash
# Activate your environment (Windows)
.venv\Scripts\activate

# Start the upload API
python app/start_api.py
```
> The backend runs on `http://localhost:8000`.

### 2. Frontend (React/Vite)
Open another terminal, navigate to the `front-end` directory:
```bash
cd front-end

# Start the development server
npm run dev
```
> The frontend typically runs on `http://localhost:5173`. Open this URL in your web browser to view the `AIAgentSpace` interface.

### 3. Background Services (RabbitMQ Consumers)
*(Optional depending on your `PIPELINE_TRIGGER_MODE`)*
If your pipeline uses asynchronous message queuing via RabbitMQ instead of running immediately after upload in the background process, you must run the consumer script:
```bash
# Activate your environment (Windows)
.venv\Scripts\activate

# Start listening to message queues
python rabbitmq_server/start_consumer.py
```

## Pipeline Workflow Details

Once everything is booted up, here is what happens when you use the app:
1. You **drag and drop a PDF file** in the built-in React UI (`AIAgentSpace.tsx`).
2. The UI sends a POST request to `http://localhost:8000/upload`.
3. The **FastAPI Backend** stores the file inside **MinIO** and saves the `document` record, including metadata and relations, to the local **PostgreSQL** database.
4. Using the `_run_pipeline_background` method, the FastAPI application immediately:
   - Fetches the exact file from MinIO securely.
   - Runs **OCR (Optical Character Recognition)** via PaddleOCR API or local fallback.
   - Passes text to the **NLP Pipeline** for cleaning, language detection, and metadata extraction.
   - Forwards resulting elements to the **Indexer** (usually connecting to vector storage embeddings).
5. The processed chunks are securely updated and can be tracked in the PostgreSQL interface or the connected UI agent interface!

## Troubleshooting & Tips

- **Database Errors?** Ensure PostgreSQL has created the proper tables. You may need to run `alembic upgrade head` from inside `/app/` inside your python terminal to migrate the database schema correctly.
- **Port Conflicts?** Verify that ports `8000` (FastAPI), `5173` (Vite), `9000/9001` (MinIO), `5432` (PostgreSQL), and `5672/15672` (RabbitMQ) are entirely free before starting.
- **Missing Dependencies?** Check `requirements.txt` and `package.json` configurations. If you are missing paddle OCR specific modules, enforce a strict version install.
- **Pipeline Failures?** Ensure that the `PADDLE_API_TOKEN` resides securely within your root `.env` config.

---
*Happy Parsing!* 🚀