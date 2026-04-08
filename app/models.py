import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, Boolean, DateTime, Index, text, Text, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from app.database import Base


class PGVector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    def get_col_spec(self, **kw):
        return f"vector({self.dimensions})"

    # Tells Alembic how to render this type in a generated migration file
    def __repr__(self):
        return f"PGVector({self.dimensions})"

    # Lets Alembic detect if the type changed between runs
    def __eq__(self, other):
        return isinstance(other, PGVector) and self.dimensions == other.dimensions

    def __hash__(self):
        return hash((self.__class__.__name__, self.dimensions))


class PGSparseVector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    def get_col_spec(self, **kw):
        return f"sparsevec({self.dimensions})"

    def __repr__(self):
        return f"PGSparseVector({self.dimensions})"

    def __eq__(self, other):
        return isinstance(other, PGSparseVector) and self.dimensions == other.dimensions

    def __hash__(self):
        return hash((self.__class__.__name__, self.dimensions))


class Document(Base):
    __tablename__ = "documents"

    # id: UUID with auto-generation on the DB side
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()")
    )
   
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    updated_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
   
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100))
    language: Mapped[Optional[str]] = mapped_column(String(10), index=True)
   
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="pending", index=True)
    doc_metadata: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, server_default=text("'{}'::jsonb"))
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
   
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=datetime.now(timezone.utc)
    )

    # Partial Index for is_deleted
    __table_args__ = (
        Index(
            "ix_documents_is_deleted",
            "is_deleted",
            postgresql_where=(is_deleted == False)
        ),
    )

    def __repr__(self):
        return f'<Document {self.filename}>'


class Chunk(Base):
    __tablename__ = "chunks"

    chunk_id: Mapped[str] = mapped_column(Text, primary_key=True)
    doc_id: Mapped[str] = mapped_column(Text, nullable=False)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
    )

    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    block_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    block_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_lang: Mapped[str] = mapped_column(Text, nullable=False)

    text_original: Mapped[str] = mapped_column(Text, nullable=False)
    text_en: Mapped[str] = mapped_column(Text, nullable=False)

    section_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    translation_failed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    bbox: Mapped[Optional[list[float]]] = mapped_column(ARRAY(Float), nullable=True)
    dense_vec: Mapped[Optional[str]] = mapped_column(PGVector(1024), nullable=True)
    sparse_vec: Mapped[Optional[str]] = mapped_column(PGSparseVector(250002), nullable=True)

    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index("ix_chunks_document_id", "document_id"),
        Index("ix_chunks_doc_id", "doc_id"),
        Index("ix_chunks_block_type", "block_type"),
        Index("ix_chunks_source_lang", "source_lang"),
    )

    def __repr__(self):
        return f"<Chunk {self.chunk_id}>"
