# Complete Integration Testing Guide

## Overview
This guide shows how to test the complete workflow:
**Upload API → RabbitMQ → OCR Consumer → Database Update**

---

## Architecture Flow

```
1. User uploads PDF via API (app/api.py)
   ↓
2. File stored in MinIO
   ↓
3. Document record created in PostgreSQL (status: "uploaded")
   ↓
4. Message sent to RabbitMQ queue (ingestion.py)
   ↓
5. Document status updated to "processing"
   ↓
6. OCR Consumer receives message (ocr_services.py)
   ↓
7. OCR processing performed
   ↓
8. Document status updated to "completed"
```

---

## Prerequisites

### 1. Install Required Packages
```powershell
pip install pika python-dotenv fastapi sqlalchemy minio psycopg2-binary alembic
```

### 2. Start All Services

**Terminal 1 - PostgreSQL:**
```powershell
cd C:\P2M\postgres_server
docker-compose up -d
```

**Terminal 2 - MinIO:**
```powershell
cd C:\P2M\minio_server
docker-compose up -d
```

**Terminal 3 - RabbitMQ:**
```powershell
cd C:\P2M\rabbitmq_server
docker-compose up -d
```

### 3. Verify All Services Running
```powershell
docker ps
```
Should show: `postgres`, `minio`, `rabbitmq-server`

---

## Step-by-Step Integration Testing

### **Step 1: Start the API Server**

**Terminal 4:**
```powershell
cd C:\P2M
python app/start_api.py
```

**Expected Output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

**Verify:** Open http://localhost:8000/docs (FastAPI Swagger UI)

---

### **Step 2: Start the OCR Consumer**

**Terminal 5:**
```powershell
cd C:\P2M\rabbitmq_server
python start_consumer.py
```

**Expected Output:**
```
============================================================
OCR Consumer Service Started
============================================================
Connected to RabbitMQ at localhost
Waiting for OCR jobs. Press CTRL+C to exit
============================================================
```

---

### **Step 3: Upload a Test Document**

**Option A - Using cURL:**
```powershell
curl -X POST "http://localhost:8000/upload" `
  -F "file=@test.pdf" `
  -F "language=en"
```

**Option B - Using Python:**
```python
import requests

with open('test.pdf', 'rb') as file:
    response = requests.post(
        'http://localhost:8000/upload',
        files={'file': file},
        data={'language': 'en'}
    )
    print(response.json())
```

**Option C - Using FastAPI Docs:**
1. Go to http://localhost:8000/docs
2. Click on `/upload` endpoint
3. Click "Try it out"
4. Upload a PDF file
5. Click "Execute"

---

### **Step 4: Watch the Flow**

**In Terminal 4 (API):**
```
INFO:     "POST /upload HTTP/1.1" 201 Created
```

**In Terminal 5 (Consumer):**
```
[OCR] Processing document: 12345678-1234-1234-1234-123456789abc
      URL: http://localhost:9000/pdf-storage/1234567890-test.pdf
      Source: user_upload
[OCR] Simulating OCR processing for test.pdf...
[OCR] ✓ Successfully processed document 12345678-1234-1234-1234-123456789abc
```

---

### **Step 5: Verify in RabbitMQ Management UI**

1. **Open:** http://localhost:15672
2. **Login:** admin / secretpassword
3. **Go to Queues tab**
4. **Click on `ocr_queue`**
5. **Observe:**
   - Message rate graph showing activity
   - Consumer count: 1
   - Messages getting processed (Ready count goes down)

---

### **Step 6: Verify in Database**

**Option A - Using psql:**
```powershell
docker exec -it postgres-container psql -U postgres
```

```sql
SELECT id, filename, status, created_at, updated_at 
FROM documents 
ORDER BY created_at DESC 
LIMIT 5;
```

**Expected statuses:**
- `uploaded` → initially
- `processing` → after message sent
- `completed` → after OCR finished

**Option B - Using Python:**
```python
import psycopg2

conn = psycopg2.connect(
    "postgresql://postgres:123456789@localhost:5432/postgres"
)
cur = conn.cursor()

cur.execute("""
    SELECT id, filename, status, doc_metadata 
    FROM documents 
    ORDER BY created_at DESC 
    LIMIT 1
""")

doc = cur.fetchone()
print(f"Document: {doc[1]}")
print(f"Status: {doc[2]}")
print(f"Metadata: {doc[3]}")
```

---

### **Step 7: Check MinIO Storage**

1. **Open:** http://localhost:9001 (MinIO Console)
2. **Login:** admin / password123
3. **Browse:** `pdf-storage` bucket
4. **Verify:** Your uploaded file is there with timestamp prefix

---

## Complete Test Scenario

### Test Case: Upload and Process Document

**Setup:**
- All services running (PostgreSQL, MinIO, RabbitMQ)
- API server running
- Consumer running

**Steps:**
1. Upload PDF via API
2. Check API response - should return document with `status: "processing"`
3. Wait 2-3 seconds
4. Check consumer logs - should show processing completion
5. Query database - status should be `completed`
6. Check RabbitMQ UI - message should be consumed
7. Check MinIO - file should exist

**Expected Results:**
- ✓ File uploaded to MinIO
- ✓ Document created in database
- ✓ Message sent to RabbitMQ
- ✓ Consumer processes message
- ✓ Status transitions: uploaded → processing → completed
- ✓ OCR metadata added to document

---

## Monitoring Commands

### Check All Docker Services
```powershell
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### Watch RabbitMQ Logs
```powershell
docker logs -f rabbitmq-server
```

### Monitor Queue in Real-time
```powershell
docker exec rabbitmq-server rabbitmqctl list_queues
```

### Check Database Records
```powershell
docker exec -it postgres-container psql -U postgres -c "SELECT COUNT(*) FROM documents;"
```

---

## Troubleshooting

### Issue: API can't send to RabbitMQ
**Solution:**
1. Check RabbitMQ is running: `docker ps`
2. Check connection in API logs
3. Verify credentials match in docker-compose.yml

### Issue: Consumer not receiving messages
**Solution:**
1. Check consumer is running
2. Verify queue name matches (`ocr_queue`)
3. Check RabbitMQ UI for consumer connection

### Issue: Database connection fails
**Solution:**
1. Verify PostgreSQL is running
2. Check DATABASE_URL in app/database.py
3. Test connection: `docker exec -it postgres-container psql -U postgres`

### Issue: MinIO upload fails
**Solution:**
1. Check MinIO is running
2. Verify credentials in .env or api.py
3. Ensure bucket exists (created on startup)

---

## Performance Testing

### Test Multiple Uploads
```python
import requests
import concurrent.futures

def upload_file(file_path):
    with open(file_path, 'rb') as f:
        response = requests.post(
            'http://localhost:8000/upload',
            files={'file': f}
        )
    return response.status_code

# Upload 10 files concurrently
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(upload_file, 'test.pdf') for _ in range(10)]
    results = [f.result() for f in futures]
    
print(f"Success rate: {results.count(201)}/10")
```

### Test Consumer Throughput
1. Send 100 messages to queue
2. Monitor processing time
3. Check for any failures or delays

---

## Success Checklist

- [ ] All 4 Docker containers running
- [ ] API accessible at http://localhost:8000
- [ ] RabbitMQ UI accessible at http://localhost:15672
- [ ] MinIO Console accessible at http://localhost:9001
- [ ] Can upload PDF successfully
- [ ] Message appears in RabbitMQ queue
- [ ] Consumer processes message
- [ ] Document status updates in database
- [ ] File visible in MinIO storage
- [ ] No errors in any logs

---

## Next Steps

After successful integration testing:

1. **Implement Real OCR:**
   - Replace simulated processing in `ocr_services.py`
   - Add actual OCR engine (Tesseract, Textract, etc.)
   - Extract and store real text content

2. **Add Error Handling:**
   - Implement retry logic
   - Set up dead letter queue
   - Add logging and monitoring

3. **Scale Consumer:**
   - Run multiple consumer instances
   - Test load distribution
   - Monitor performance

4. **Add Endpoints:**
   - GET /documents - List all documents
   - GET /documents/{id} - Get document details
   - GET /documents/{id}/status - Check processing status

5. **Frontend Integration:**
   - Build upload UI
   - Show processing status
   - Display OCR results
