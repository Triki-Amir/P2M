# Agent AI Database Integration

This document explains the database integration for the Agent AI tab's PDF upload functionality.

## Overview

The Agent AI tab now includes a complete database system that:
1. Stores PDF files in MinIO object storage
2. Saves document metadata in a PostgreSQL database (direct connection)
3. Provides a seamless upload experience in the frontend

## Architecture

```
Frontend (AIAgentSpace.tsx)
    ↓ (HTTP POST)
Backend (server.js)
    ↓ (Store file)
MinIO Server
    ↓ (Save metadata)
PostgreSQL (documents table)
```

## Setup Instructions

### 1. Database Setup

First, set up your local PostgreSQL database and apply the migration:

**Using psql:**
```bash
# Create database (if not exists)
createdb p2m_database

# Or connect to an existing database
psql -d your_database_name

# Run the migration
psql -d p2m_database -f backend/minio-backend/migrations/001_create_documents_table.sql
```

**Using a GUI tool (pgAdmin, DBeaver, etc.):**
1. Connect to your local PostgreSQL server
2. Create a new database (e.g., `p2m_database`)
3. Open and execute the SQL file: `backend/minio-backend/migrations/001_create_documents_table.sql`

### 2. Backend Setup

```bash
cd backend/minio-backend

# Install dependencies
npm install

# Configure environment (copy and edit .env)
cp .env.example .env
# Edit .env with your PostgreSQL connection details:
# - DATABASE_URL=postgresql://username:password@localhost:5432/p2m_database
# OR
# - PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD

# Start the backend server
node server.js
```

The backend will run on http://localhost:3000

### 3. MinIO Setup

Make sure MinIO is running locally:

```bash
# If using Docker:
docker run -p 9000:9000 -p 9001:9001 \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=minioadmin" \
  minio/minio server /data --console-address ":9001"
```

Then create the bucket:
1. Open MinIO Console: http://localhost:9001
2. Login with minioadmin/minioadmin
3. Create a bucket named "pdf-storage"

### 4. Frontend Setup

```bash
cd front-end

# Install dependencies (if not already done)
npm install

# Start the development server
npm run dev
```

## Configuration

### Environment Variables

Edit `backend/minio-backend/.env` to configure:

- **MinIO Settings**: Endpoint, port, access keys, bucket name
- **PostgreSQL Settings**: Connection URL or individual connection parameters (host, port, database, user, password)
- **Server Settings**: Port number
- **Tenant Settings**: Default tenant ID for multi-tenant support

## Database Schema

The `documents` table includes:

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key (auto-generated) |
| tenant_id | UUID | For multi-tenant support |
| uploaded_by | UUID | User who uploaded (optional) |
| filename | VARCHAR(255) | Original filename |
| storage_path | VARCHAR(500) | Path in MinIO |
| file_size | INTEGER | File size in bytes |
| mime_type | VARCHAR(100) | MIME type (e.g., application/pdf) |
| status | VARCHAR(50) | Processing status (default: 'pending') |
| metadata | JSONB | Additional metadata |
| is_deleted | BOOLEAN | Soft delete flag |
| created_at | TIMESTAMP | Creation timestamp |
| updated_at | TIMESTAMP | Last update timestamp |

## API Endpoints

### POST /upload

Uploads a PDF file to MinIO and saves metadata to PostgreSQL.

**Request:**
- Method: POST
- Content-Type: multipart/form-data
- Body: File with key "file"

**Response:**
```json
{
  "message": "PDF uploaded successfully",
  "fileName": "1234567890-document.pdf",
  "documentId": "uuid-here",
  "storagePath": "1234567890-document.pdf"
}
```

**Error Response:**
```json
{
  "error": "Error message",
  "details": "Detailed error message"
}
```

## Testing

1. Start the backend: `node backend/minio-backend/server.js`
2. Start the frontend: `npm run dev` (in front-end directory)
3. Navigate to the Agent AI tab
4. Drag and drop a PDF file
5. Check the database to verify the record was created:
   - Connect to your PostgreSQL database using psql or a GUI tool
   - Query the documents table: `SELECT * FROM documents ORDER BY created_at DESC LIMIT 5;`
   - You should see the new record

## Troubleshooting

### Backend not connecting to database
- Verify PostgreSQL connection parameters in `.env`
- Ensure PostgreSQL is running: `pg_isready` or check service status
- Check that the documents table exists in your database
- Test connection: `psql -d your_database_name -c "SELECT 1;"`

### MinIO upload fails
- Ensure MinIO is running on localhost:9000
- Verify the bucket "pdf-storage" exists
- Check MinIO credentials in `.env`

### CORS errors in frontend
- The backend has CORS enabled for all origins
- If issues persist, check browser console for details

### File not showing in database
- Check backend console for error messages
- Verify the migration was applied correctly
- Test the /upload endpoint with curl or Postman

## Migration from pdfuploader.html

The previous standalone `pdfuploader.html` has been replaced with:
- Integrated upload in `AIAgentSpace.tsx` component
- Direct backend API calls instead of separate HTML file
- Database persistence for all uploaded documents

The old HTML file is kept for reference but is no longer used in the application.
