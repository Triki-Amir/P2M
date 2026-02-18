import uuid
import os
from datetime import datetime, timezone
from typing import Optional
from io import BytesIO

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv

from app.database import get_db, engine, Base
from app.models import Document

load_dotenv()

app = FastAPI(title="P2M Document Upload API")

# --- CONFIGURATION ---
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "pdf-storage")

minio_client = Minio(
    os.getenv("MINIO_ENDPOINT", "localhost:9000"),
    access_key=os.getenv("MINIO_ACCESS_KEY", "admin"),
    secret_key=os.getenv("MINIO_SECRET_KEY", "password123"),
    secure=os.getenv("MINIO_SECURE", "false").lower() == "true"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- HELPERS ---

def upload_to_s3(file_data: bytes, filename: str, content_type: str):
    """Encapsulated storage logic."""
    try:
        minio_client.put_object(
            MINIO_BUCKET,
            filename,
            BytesIO(file_data),
            length=len(file_data),
            content_type=content_type
        )
    except S3Error as e:
        raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")

# --- EVENTS ---

@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)
    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)

# --- ROUTES ---

@app.post("/upload", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    tenant_id: Optional[uuid.UUID] = None, # FastAPI auto-parses UUID strings
    uploaded_by: Optional[uuid.UUID] = None,
    language: Optional[str] = None,
    db: Session = Depends(get_db)
):
    # 1. Validation
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # 2. Prepare Metadata
    file_content = await file.read()
    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    storage_filename = f"{timestamp}-{file.filename or 'unnamed.pdf'}"

    # 3. Store File (MinIO)
    upload_to_s3(file_content, storage_filename, file.content_type)

    # 4. Save Record (Database)
    try:
        new_doc = Document(
            tenant_id=tenant_id or uuid.UUID("00000000-0000-0000-0000-000000000000"),
            uploaded_by=uploaded_by,
            created_by=uploaded_by,
            updated_by=uploaded_by,
            filename=file.filename or 'unnamed.pdf',
            storage_path=storage_filename,
            file_size=len(file_content),
            mime_type=file.content_type,
            language=language,
            status="uploaded",
            processing_notes=None,
            doc_metadata={}
        )
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        return new_doc  # FastAPI automatically serializes the model to JSON
    except Exception as e:
        db.rollback()
        # Note: In a real app, you'd delete the MinIO file here if DB fails
        raise HTTPException(status_code=500, detail="Database save failed")
