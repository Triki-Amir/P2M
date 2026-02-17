# Database Migrations

This directory contains SQL migration files for the documents table.

## Running Migrations

To apply the migrations to your Supabase/PostgreSQL database:

1. Open your Supabase project dashboard
2. Go to the SQL Editor
3. Copy and paste the content of `001_create_documents_table.sql`
4. Execute the SQL

Alternatively, if you have psql installed:

```bash
psql -h your-supabase-host -U postgres -d postgres -f migrations/001_create_documents_table.sql
```

## Schema Overview

The `documents` table stores metadata for uploaded PDF files with the following key fields:

- `id`: Unique identifier (UUID)
- `tenant_id`: Multi-tenant support
- `filename`: Original filename
- `storage_path`: Path to the file in MinIO
- `file_size`: Size in bytes
- `mime_type`: File MIME type
- `status`: Processing status (pending, processed, failed)
- `metadata`: Additional JSON metadata
- `is_deleted`: Soft delete flag
- `created_at`, `updated_at`: Timestamps
