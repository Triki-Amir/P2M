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
from rabbitmq_server.Producers.ingestion import trigger_ingestion

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
            doc_metadata={}
        )
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        
        # 5. Trigger OCR Processing via RabbitMQ
        try:
            # Construct MinIO URL for the uploaded file
            minio_endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
            file_url = f"http://{minio_endpoint}/{MINIO_BUCKET}/{storage_filename}"
            
            # Trigger ingestion to RabbitMQ queue
            trigger_ingestion(doc_id=str(new_doc.id), file_url=file_url)
            
            # Update status to processing
            new_doc.status = "processing"
            db.commit()
            db.refresh(new_doc)
        except Exception as mq_error:
            # Log the error but don't fail the upload
            print(f"Warning: Failed to trigger OCR processing: {mq_error}")
            # Document is uploaded but not queued for processing
        
        return new_doc  # FastAPI automatically serializes the model to JSON
    except Exception as e:
        db.rollback()
        # Note: In a real app, you'd delete the MinIO file here if DB fails
        raise HTTPException(status_code=500, detail="Database save failed")


# --- DOCUMENT QUERY ROUTES ---

@app.get("/documents/{doc_id}")
def get_document(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return a single document record including its OCR results."""
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@app.get("/documents/{doc_id}/status")
def get_document_status(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return only the processing status for a document."""
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"id": str(document.id), "status": document.status}


@app.get("/documents/{doc_id}/text")
def get_document_text(doc_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return the extracted OCR text for a completed document."""
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Document is not yet processed (status: {document.status})",
        )
    metadata = document.doc_metadata or {}
    return {
        "id": str(document.id),
        "filename": document.filename,
        "text_extracted": metadata.get("text_extracted", ""),
        "page_count": metadata.get("page_count", 0),
        "languages": metadata.get("languages", ""),
        "pages": metadata.get("pages", []),
    }
