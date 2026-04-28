import uuid
import os
import traceback
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
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
import fitz  # PyMuPDF

from ingestion_service.database import get_db, engine, Base, SessionLocal
from ingestion_service.models import Document, Tenant, User, Role, Notification
from ingestion_service.producer import trigger_ingestion
from run_pipeline import main as run_local_pipeline

load_dotenv()

app = FastAPI(title="P2M Document Upload API")

# --- CONFIGURATION ---
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "pdf-storage")
PIPELINE_TRIGGER_MODE = os.getenv("PIPELINE_TRIGGER_MODE", "rabbitmq").strip().lower()
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


def _create_notification_db(
    db: Session,
    tenant_id: uuid.UUID,
    document_id: Optional[uuid.UUID],
    type_: str,
    category: str,
    title: str,
    description: str,
):
    """Create a notification, skipping silently if one already exists for this document+category."""
    try:
        if document_id is not None:
            existing = db.query(Notification).filter(
                Notification.document_id == document_id,
                Notification.category == category,
            ).first()
            if existing:
                return
        notif = Notification(
            tenant_id=tenant_id,
            document_id=document_id,
            type=type_,
            category=category,
            title=title,
            description=description,
        )
        db.add(notif)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Warning: Failed to create notification ({category}): {e}")


def _check_deadline_notifications(tenant_id: uuid.UUID, db: Session):
    """Check DocumentCompliance records for approaching deadlines and create warnings."""
    from ingestion_service.models import DocumentCompliance
    from datetime import date as date_type

    try:
        results = (
            db.query(DocumentCompliance, Document)
            .join(Document, DocumentCompliance.document_id == Document.id)
            .filter(DocumentCompliance.tenant_id == tenant_id)
            .all()
        )
        today = datetime.now(timezone.utc).date()
        for comp, doc in results:
            if not comp.extracted_criteria:
                continue
            deadline_str = comp.extracted_criteria.get("admin_criteria", {}).get("deadline")
            if not deadline_str or deadline_str in ("null", None):
                continue
            try:
                deadline_date = date_type.fromisoformat(str(deadline_str))
                days_until = (deadline_date - today).days
                if 0 <= days_until <= 2:
                    if days_until == 0:
                        desc = f'La date limite pour "{doc.filename}" est aujourd\'hui.'
                    elif days_until == 1:
                        desc = f'La date limite pour "{doc.filename}" est demain.'
                    else:
                        desc = f'La date limite pour "{doc.filename}" est dans {days_until} jours.'
                    _create_notification_db(
                        db=db,
                        tenant_id=tenant_id,
                        document_id=doc.id,
                        type_="warning",
                        category="deadline_warning",
                        title="Date Limite Approchante",
                        description=desc,
                    )
            except (ValueError, TypeError):
                continue
    except Exception as e:
        print(f"Warning: Deadline notification check failed: {e}")


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
        if status == "completed":
            _create_notification_db(
                db=db,
                tenant_id=doc.tenant_id,
                document_id=doc.id,
                type_="info",
                category="analyse_complete",
                title="Analyse IA Terminée",
                description=f'Votre document "{doc.filename}" a été traité.',
            )
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

@app.get("/ao/tenders/{tenant_id}", status_code=200)
def get_all_ao(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    from ingestion_service.models import DocumentCompliance, Document
    results = db.query(DocumentCompliance, Document).join(
        Document, DocumentCompliance.document_id == Document.id
    ).filter(
        DocumentCompliance.tenant_id == tenant_id
    ).all()
    
    def get_first(criteria, category, key, default="N/A"):
        if not criteria or not isinstance(criteria, dict):
            return default
        cat = criteria.get(category, {})
        if not cat or not isinstance(cat, dict):
            return default
        val = cat.get(key)
        if isinstance(val, list) and len(val) > 0:
            return str(val[0])
        elif isinstance(val, str) and val:
            return val
        return default

    return [
        {
            "id": str(doc.id),
            "organizationName": doc.doc_metadata.get("organization_name", "Inconnu") if doc.doc_metadata else "Inconnu",
            "isCompliant": comp.is_compliant,
            "deadline": get_first(comp.extracted_criteria, "admin_criteria", "deadline", "N/A"),
            "chiffreAffaireMinimal": get_first(comp.extracted_criteria, "financial_criteria", "annual_revenue", "N/A"),
            "certificat": get_first(comp.extracted_criteria, "technical_criteria", "certifications", "N/A"),
        }
        for comp, doc in results
    ]

@app.get("/ao/compliant/{tenant_id}", status_code=200)
def get_compliant_ao(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Called by the UI Appel d'Offre (AO) page to list all documents 
    that match society criteria.
    """
    from ingestion_service.models import DocumentCompliance, Document
    results = db.query(DocumentCompliance, Document).join(
        Document, DocumentCompliance.document_id == Document.id
    ).filter(
        DocumentCompliance.tenant_id == tenant_id,
        DocumentCompliance.is_compliant == True
    ).all()
    
    return [
        {
            "compliance_id": str(comp.id),
            "document_id": str(doc.id),
            "filename": doc.filename,
            "status": "COMPLIANT",
            "extracted_criteria": comp.extracted_criteria,
            "validation_details": comp.compliance_details,
            "analyzed_at": comp.analyzed_at.isoformat()
        }
        for comp, doc in results
    ]

# --- EOF ---

# --- NOTIFICATIONS ---

@app.get("/notifications/by-tenant/{tenant_id}", status_code=200)
def get_notifications(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return all notifications for a tenant, checking for new deadline warnings first."""
    _check_deadline_notifications(tenant_id, db)
    notifications = (
        db.query(Notification)
        .filter(Notification.tenant_id == tenant_id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(n.id),
            "type": n.type,
            "category": n.category,
            "title": n.title,
            "description": n.description,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat(),
        }
        for n in notifications
    ]


@app.get("/notifications/by-tenant/{tenant_id}/unread-count", status_code=200)
def get_unread_count(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return the number of unread notifications for a tenant."""
    count = (
        db.query(Notification)
        .filter(Notification.tenant_id == tenant_id, Notification.is_read == False)
        .count()
    )
    return {"count": count}


@app.patch("/notifications/{notification_id}/read", status_code=200)
def mark_notification_read(notification_id: uuid.UUID, db: Session = Depends(get_db)):
    """Mark a single notification as read."""
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    notif.is_read = True
    db.commit()
    return {"message": "Marked as read"}


@app.delete("/notifications/{notification_id}", status_code=200)
def dismiss_notification(notification_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete (dismiss) a single notification."""
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    db.delete(notif)
    db.commit()
    return {"message": "Notification dismissed"}


@app.delete("/notifications/by-tenant/{tenant_id}", status_code=200)
def clear_all_notifications(tenant_id: uuid.UUID, db: Session = Depends(get_db)):
    """Delete all notifications for a tenant."""
    db.query(Notification).filter(Notification.tenant_id == tenant_id).delete()
    db.commit()
    return {"message": "All notifications cleared"}


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
        
    if tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
    else:
        tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

    # 2. Prepare Metadata
    file_content = await file.read()
    
    # 2.b Extract PDF metadata (page count)
    page_count = 0
    try:
        pdf_stream = BytesIO(file_content)
        with fitz.open(stream=pdf_stream, filetype="pdf") as doc:
            page_count = len(doc)
    except Exception as e:
        print(f"Error extracting PDF metadata: {e}")

    timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    storage_filename = f"{timestamp}-{file.filename or 'unnamed.pdf'}"

    # 3. Store File (MinIO)
    upload_to_s3(file_content, storage_filename, file.content_type)

    # 4. Save Record (Database)
    try:
        new_doc = Document(
            tenant_id=tenant_id,
            uploaded_by=uploaded_by,
            created_by=uploaded_by,
            updated_by=uploaded_by,
            filename=file.filename or 'unnamed.pdf',
            storage_path=storage_filename,
            file_size=len(file_content),
            mime_type=file.content_type,
            language=language,
            status="uploaded",
            doc_metadata={
                "page_count": page_count,
                "file_size_bytes": len(file_content)
            }
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
                trigger_ingestion(
                    doc_id=str(new_doc.id), 
                    file_url=file_url,
                    tenant_id=str(new_doc.tenant_id),
                    storage_path=f"{MINIO_BUCKET}/{storage_filename}",
                    filename=file.filename or "unnamed.pdf"
                )

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
