import uuid
import os
import traceback
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional
from io import BytesIO
from pathlib import Path
from sqlalchemy import text
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from app.database import get_db, engine, Base, SessionLocal
from app.models import Document, Tenant, User, Role
from rabbitmq_server.Producers.ingestion import trigger_ingestion
from run_pipeline import main as run_local_pipeline

load_dotenv()

app = FastAPI(title="P2M Document Upload API")

# --- CONFIGURATION ---
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "pdf-storage")
PIPELINE_TRIGGER_MODE = os.getenv("PIPELINE_TRIGGER_MODE", "run_pipeline").strip().lower()
UPLOAD_TEMP_ROOT = Path(os.getenv("UPLOAD_TEMP_ROOT", Path(__file__).resolve().parents[1] / "temp" / "uploads"))

minio_client = Minio(
    os.getenv("MINIO_ENDPOINT", "localhost:9000"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
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


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(32)
    iterations = 600000
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_str, salt, digest = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        check = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            int(iterations_str),
        ).hex()
        return secrets.compare_digest(check, digest)
    except Exception:
        return False


def _update_document_status(doc_id: str, status: str, extra_metadata: Optional[dict] = None):
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == uuid.UUID(doc_id)).first()
        if not doc:
            return

        doc.status = status
        doc.updated_at = datetime.now(timezone.utc)
        if extra_metadata:
            doc.doc_metadata = {
                **(doc.doc_metadata or {}),
                **extra_metadata,
            }
        db.commit()
    finally:
        db.close()


def _run_pipeline_background(doc_id: str, original_filename: str, storage_filename: str):
    """
    Runs local OCR->NLP->Indexer pipeline by downloading the file from MinIO in background.
    The PDF basename is preserved so indexer can resolve documents.filename.
    """
    work_dir = UPLOAD_TEMP_ROOT / doc_id
    work_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = work_dir / (original_filename or "unnamed.pdf")

    try:
        # Download the file from MinIO
        minio_client.fget_object(MINIO_BUCKET, storage_filename, str(pdf_path))
        
        run_local_pipeline(str(pdf_path))

        _update_document_status(
            doc_id,
            "completed",
            {
                "pipeline_mode": "run_pipeline",
                "processed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        _update_document_status(
            doc_id,
            "failed",
            {
                "pipeline_mode": "run_pipeline",
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "failed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
    finally:
        try:
            if pdf_path.exists():
                pdf_path.unlink()
            if work_dir.exists() and not any(work_dir.iterdir()):
                work_dir.rmdir()
        except Exception:
            # Cleanup failure should not affect processing result
            pass

# --- EVENTS ---

@app.on_event("startup")
async def startup_event():
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    if not minio_client.bucket_exists(MINIO_BUCKET):
        minio_client.make_bucket(MINIO_BUCKET)

# --- ROUTES ---


class SignupRequest(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=255)
    tenant_email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=2, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    tenant_email: str = Field(min_length=3, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=128)


class TenantMetadataUpdate(BaseModel):
    geo_zone: Optional[str] = None
    guarantee: Optional[str] = None
    annual_revenue: Optional[float] = None
    certifications: Optional[list[str]] = None
    staff_count: Optional[dict] = None  # e.g. {"engineers": 10, "technicians": 5}

    class Config:
        extra = "allow"


@app.post("/auth/signup", status_code=201)
def auth_signup(payload: SignupRequest, db: Session = Depends(get_db)):
    tenant_email = _normalize_email(payload.tenant_email)
    user_email = _normalize_email(payload.email)

    tenant_name = payload.tenant_name.strip()
    existing_tenant_by_email = db.query(Tenant).filter(Tenant.email == tenant_email).first()
    if existing_tenant_by_email:
        raise HTTPException(status_code=409, detail="Tenant already exists")

    existing_tenant_by_name = db.query(Tenant).filter(Tenant.name == tenant_name).first()
    if existing_tenant_by_name:
        raise HTTPException(status_code=409, detail="Tenant already exists")

    tenant = Tenant(
        name=tenant_name,
        email=tenant_email,
        subscription_plan="free",
        tenant_metadata={},
    )
    db.add(tenant)
    db.flush()

    employer_role = db.query(Role).filter(Role.name == "employer").first()
    if not employer_role:
        employer_role = Role(name="employer", description="Default employer role")
        db.add(employer_role)
        db.flush()

    existing_user = db.query(User).filter(
        User.tenant_id == tenant.id,
        User.email == user_email,
    ).first()
    if existing_user:
        db.rollback()
        raise HTTPException(status_code=409, detail="User already exists for this tenant")

    user = User(
        tenant_id=tenant.id,
        role_id=employer_role.id,
        email=user_email,
        hashed_password=_hash_password(payload.password),
        full_name=payload.full_name.strip(),
        user_metadata={},
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "message": "Employer account created successfully",
        "tenant_id": str(tenant.id),
        "user_id": str(user.id),
    }


@app.post("/auth/login")
def auth_login(payload: LoginRequest, db: Session = Depends(get_db)):
    tenant_email = _normalize_email(payload.tenant_email)
    user_email = _normalize_email(payload.email)

    tenant = db.query(Tenant).filter(Tenant.email == tenant_email).first()
    if not tenant or not tenant.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = db.query(User).filter(
        User.tenant_id == tenant.id,
        User.email == user_email,
        User.is_deleted.is_(False),
    ).first()

    if not user or not user.is_active or not _verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "message": "Login successful",
        "tenant": {
            "id": str(tenant.id),
            "name": tenant.name,
            "email": tenant.email,
            "metadata": tenant.tenant_metadata or {},
        },
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
        },
    }


@app.get("/tenants/{tenant_id}", status_code=200)
def get_tenant(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "email": tenant.email,
        "metadata": tenant.tenant_metadata or {},
    }


@app.patch("/tenants/{tenant_id}/metadata", status_code=200)
def update_tenant_metadata(
    tenant_id: uuid.UUID, 
    payload: TenantMetadataUpdate, 
    db: Session = Depends(get_db)
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Use model_dump for Pydantic v2, or dict() for v1
    try:
        new_data = payload.model_dump(exclude_unset=True)
    except AttributeError:
        new_data = payload.dict(exclude_unset=True)
    
    current_metadata = tenant.tenant_metadata or {}
    tenant.tenant_metadata = {**current_metadata, **new_data}
    
    # Force SQLAlchemy to recognize the JSON change
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(tenant, "tenant_metadata")
    
    tenant.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(tenant)
    return {"message": "Tenant metadata updated", "metadata": tenant.tenant_metadata}


@app.post("/upload", status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
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
        
        # 5. Trigger processing after upload.
        if PIPELINE_TRIGGER_MODE == "run_pipeline":
            new_doc.status = "processing"
            new_doc.doc_metadata = {
                **(new_doc.doc_metadata or {}),
                "pipeline_mode": "run_pipeline",
                "queued_at": datetime.now(timezone.utc).isoformat(),
            }
            db.commit()
            db.refresh(new_doc)

            # Launch OCR->NLP->Indexer in background right after UI upload.
            background_tasks.add_task(
                _run_pipeline_background,
                str(new_doc.id),
                file.filename or "unnamed.pdf",
                storage_filename,
            )
        else:
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
