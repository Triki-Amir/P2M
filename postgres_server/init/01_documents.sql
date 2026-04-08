-- 01_documents.sql
-- Existing ingestion pipeline schema — unchanged.
-- Runs first so chunks can foreign-key against documents.id

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS documents (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID NOT NULL,
    uploaded_by UUID,
    created_by  UUID,
    updated_by  UUID,
    filename    VARCHAR(255) NOT NULL,
    storage_path VARCHAR(500) NOT NULL,
    file_size   INTEGER,
    mime_type   VARCHAR(100),
    language    VARCHAR(10),
    status      VARCHAR(50) NOT NULL DEFAULT 'pending',
    metadata    JSONB DEFAULT '{}'::jsonb,
    is_deleted  BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_documents_tenant_id   ON documents (tenant_id);
CREATE INDEX IF NOT EXISTS ix_documents_uploaded_by ON documents (uploaded_by);
CREATE INDEX IF NOT EXISTS ix_documents_status      ON documents (status);
CREATE INDEX IF NOT EXISTS ix_documents_language    ON documents (language);
CREATE INDEX IF NOT EXISTS ix_documents_created_at  ON documents (created_at);
CREATE INDEX IF NOT EXISTS ix_documents_is_deleted  ON documents (is_deleted)
    WHERE is_deleted = false;

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
