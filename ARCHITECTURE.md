# System Architecture - Complete Integration

## Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        P2M System                                │
└─────────────────────────────────────────────────────────────────┘

┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Frontend   │────▶│   FastAPI    │────▶│  PostgreSQL  │
│   (React)    │     │   (app/)     │     │   Database   │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                            ├──────────────▶ ┌──────────────┐
                            │                │    MinIO     │
                            │                │   Storage    │
                            │                └──────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │   RabbitMQ   │
                     │  Message Q   │
                     └──────┬───────┘
                            │
                            ▼
                     ┌──────────────┐
                     │ OCR Consumer │
                     │ (ocr_service)│
                     └──────┬───────┘
                            │
                            └──────────────▶ Updates DB
```

---

## Data Flow - Document Upload & Processing

### Step 1: Upload Request
```
Client → POST /upload (PDF file) → FastAPI
```

### Step 2: Storage
```
FastAPI → MinIO Storage (save PDF)
         ↓
      success
         ↓
FastAPI → PostgreSQL (create document record)
         status = "uploaded"
```

### Step 3: Queue for Processing
```
FastAPI → RabbitMQ Producer (ingestion.py)
         ↓
      Publish message: {doc_id, file_url, source}
         ↓
      ocr_queue (durable)
```

### Step 4: Status Update
```
FastAPI → PostgreSQL (update document)
         status = "processing"
```

### Step 5: Consumer Processing
```
RabbitMQ → OCR Consumer (ocr_services.py)
          ↓
       Get message
          ↓
       Fetch document from DB
          ↓
       Download from MinIO (optional)
          ↓
       Run OCR Processing
          ↓
       Update PostgreSQL
       - status = "completed"
       - metadata = {OCR results}
          ↓
       Acknowledge message
```

---

## File Connections

### API Integration
**File:** `app/api.py`
```python
from rabbitmq_server.Producers.ingestion import trigger_ingestion

# After saving document:
trigger_ingestion(doc_id=str(new_doc.id), file_url=file_url)
```

### Producer
**File:** `rabbitmq_server/Producers/ingestion.py`
```python
def trigger_ingestion(doc_id, file_url):
    # Sends message to RabbitMQ ocr_queue
```

### Consumer
**File:** `rabbitmq_server/consumers/ocr_services.py`
```python
def callback(ch, method, properties, body):
    # Receives message from RabbitMQ
    # Processes OCR
    # Updates database
```

---

## Message Format

### RabbitMQ Message Structure
```json
{
  "doc_id": "uuid-string",
  "url": "http://localhost:9000/pdf-storage/timestamp-filename.pdf",
  "source": "user_upload"
}
```

---

## Database States

### Document Status Flow
```
uploaded → processing → completed
                    ↓
                  failed (on error)
```

### Document Model
```python
{
  "id": UUID,
  "filename": str,
  "storage_path": str,
  "status": str,  # uploaded/processing/completed/failed
  "doc_metadata": dict,  # OCR results stored here
  "created_at": datetime,
  "updated_at": datetime
}
```

---

## Service Ports

| Service    | Port(s)        | Access                            |
|------------|----------------|-----------------------------------|
| FastAPI    | 8000           | http://localhost:8000             |
| PostgreSQL | 5432           | postgresql://localhost:5432       |
| MinIO      | 9000, 9001     | http://localhost:9000 (API)       |
|            |                | http://localhost:9001 (Console)   |
| RabbitMQ   | 5672, 15672    | localhost:5672 (AMQP)            |
|            |                | http://localhost:15672 (UI)       |

---

## Configuration Files

### Environment Variables
**File:** `.env`
```env
DATABASE_URL=postgresql://postgres:123456789@localhost:5432/postgres
MINIO_ENDPOINT=localhost:9000
RABBITMQ_HOST=localhost
RABBITMQ_USER=admin
RABBITMQ_PASS=secretpassword
```

### Docker Compose Files
- `postgres_server/docker-compose.yml`
- `minio_server/docker-compose.yml`
- `rabbitmq_server/docker-compose.yml`

---

## Key Integration Points

### 1. API → RabbitMQ
**Location:** [app/api.py](app/api.py)
**Function:** After document upload, triggers RabbitMQ producer
**Import:** `from rabbitmq_server.Producers.ingestion import trigger_ingestion`

### 2. RabbitMQ → Consumer
**Location:** [rabbitmq_server/consumers/ocr_services.py](rabbitmq_server/consumers/ocr_services.py)
**Function:** Listens to queue, processes OCR jobs
**Queue:** `ocr_queue` (durable)

### 3. Consumer → Database
**Location:** [rabbitmq_server/consumers/ocr_services.py](rabbitmq_server/consumers/ocr_services.py)
**Function:** Updates document status and metadata
**Import:** `from app.database import get_db_session`

---

## Testing Flow

```
1. Start Services
   ├─ docker-compose up -d (PostgreSQL)
   ├─ docker-compose up -d (MinIO)
   └─ docker-compose up -d (RabbitMQ)

2. Start Application
   ├─ python app/start_api.py
   └─ python rabbitmq_server/start_consumer.py

3. Upload Document
   └─ POST http://localhost:8000/upload

4. Verify Processing
   ├─ Check RabbitMQ UI (http://localhost:15672)
   ├─ Check consumer logs
   └─ Query database for status

5. Confirm Completion
   └─ Document status = "completed"
```

---

## Error Handling

### Upload Failures
- **MinIO Error:** HTTP 500 returned, no DB record created
- **DB Error:** HTTP 500 returned, MinIO file orphaned
- **RabbitMQ Error:** Document saved but not queued (status = "uploaded")

### Processing Failures
- **Consumer Down:** Messages accumulate in queue
- **OCR Error:** Document status set to "failed"
- **DB Update Error:** Message requeued for retry

---

## Monitoring Points

### Health Checks
1. **API Health:** `curl http://localhost:8000/docs`
2. **RabbitMQ:** Check http://localhost:15672
3. **Database:** Query documents table
4. **MinIO:** Check bucket contents

### Metrics to Monitor
- Upload success rate
- Queue depth (RabbitMQ)
- Processing time per document
- Failed document count
- Consumer throughput

---

## Quick Commands

### Check System Status
```powershell
python verify_integration.py
```

### View All Services
```powershell
docker ps
```

### Check Queue Status
```powershell
docker exec rabbitmq-server rabbitmqctl list_queues
```

### View Recent Documents
```sql
SELECT id, filename, status, created_at 
FROM documents 
ORDER BY created_at DESC 
LIMIT 10;
```

---

## Success Criteria

✓ Document uploaded via API  
✓ File stored in MinIO  
✓ Record created in PostgreSQL  
✓ Message sent to RabbitMQ  
✓ Consumer receives message  
✓ OCR processing completes  
✓ Database updated with results  
✓ Message acknowledged and removed from queue  

---

## Next Development Steps

1. Implement actual OCR processing
2. Add document download endpoint
3. Build frontend upload interface
4. Add authentication/authorization
5. Implement error retry logic
6. Set up monitoring and logging
7. Add API rate limiting
8. Scale consumer instances
