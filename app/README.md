# P2M Document Upload System

FastAPI backend that uploads PDFs to MinIO (Docker) and saves metadata to PostgreSQL.

## Quick Start

### 1. Start Docker Services
```bash
# PostgreSQL
cd C:\P2M\postgres_server
docker-compose up -d

# MinIO
cd C:\P2M\minio_server
docker-compose up -d
```

### 2. Activate Python Environment
```bash
cd C:\P2M
.venv\Scripts\activate
```

### 3. Start API Server
```bash
python -m uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```

Server runs at: **http://localhost:8000**

## Testing

### Upload a PDF
1. Open **http://localhost:8000/docs**
2. Click on `/upload` (green POST)
3. Click "Try it out"
4. Choose a PDF file
5. Click "Execute"

### Verify Upload

**Check Database (pgAdmin):**
- Host: `localhost:5432`
- User: `postgres`
- Password: `123456789`
- Database: `postgres`

```sql
SELECT id, filename, storage_path, status, created_at 
FROM documents 
ORDER BY created_at DESC;
```

**Check MinIO:**
- Open **http://localhost:9001**
- Login: `admin` / `password123`
- Bucket: `pdf-storage`

## Configuration

**Environment:** `app/.env`
```env
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=password123
MINIO_BUCKET=pdf-storage
MINIO_SECURE=false
```

**Database:** `app/database.py`
```python
DATABASE_URL = "postgresql://postgres:123456789@localhost:5432/postgres"
```

## Database Migrations

### Current Version
```bash
cd app
alembic current
```

### Make Changes
1. Edit `models.py`
2. Generate migration:
```bash
alembic revision --autogenerate -m "description"
```
3. Apply migration:
```bash
alembic upgrade head
```

### Migration History
```bash
alembic history
```

Migrations are numbered sequentially: `0001_initial.py`, `0002_add_column.py`, etc.

## Project Structure

```
app/
├── api.py              # FastAPI endpoints
├── database.py         # SQLAlchemy config
├── models.py           # Document model
├── start_api.py        # Server startup
├── alembic.ini         # Migration config
├── .env                # Environment variables
└── migrations/
    └── versions/       # Migration files
        ├── 0001_initial.py
        └── 0002_add_processing_notes_column.py
```

## Common Commands

```bash
# Start API
python -m uvicorn app.api:app --reload

# Check migration version
alembic current

# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one version
alembic downgrade -1
```

## API Endpoints

- `POST /upload` - Upload PDF (returns document metadata)
- `GET /documents` - List documents
- `GET /documents/{id}` - Get document details
- `DELETE /documents/{id}` - Soft delete document

## Troubleshooting

**Port 8000 already in use:**
```bash
netstat -ano | findstr :8000
# Kill the process or use different port
```

**Database connection error:**
```bash
# Check PostgreSQL is running
docker ps --filter "name=postgres"
```

**MinIO connection error:**
```bash
# Check MinIO is running
docker ps --filter "name=minio"
```
