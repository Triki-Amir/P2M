# Migration Guide: Supabase to PostgreSQL

This guide explains how to migrate from Supabase to direct PostgreSQL connection.

## What Changed

### 1. Backend Changes

#### Dependencies
- **Removed**: `@supabase/supabase-js` 
- **Added**: `pg` (node-postgres) for direct PostgreSQL connection
- **Added**: `express-rate-limit` for security (10 uploads per 15 minutes per IP)

#### Configuration
The `.env` file now uses PostgreSQL connection parameters instead of Supabase URL/Key:

**Old (Supabase):**
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
```

**New (PostgreSQL):**
```env
# Option 1: Connection string (recommended)
DATABASE_URL=postgresql://username:password@localhost:5432/p2m_database

# Option 2: Individual parameters
PGHOST=localhost
PGPORT=5432
PGDATABASE=p2m_database
PGUSER=your_username
PGPASSWORD=your_password
```

### 2. Frontend Changes

#### Removed Directories
- `front-end/supabase/` - Unused Supabase functions
- `front-end/utils/supabase/` - Unused Supabase configuration

#### Enhanced UI
- Added animated success banner "✓ TÉLÉCHARGEMENT RÉUSSI" after file upload
- Added spring animation to success checkmark
- Updated messages to mention PostgreSQL specifically

## Setup Instructions

### 1. Install PostgreSQL

If you don't have PostgreSQL installed locally:

**On macOS (using Homebrew):**
```bash
brew install postgresql@15
brew services start postgresql@15
```

**On Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

**On Windows:**
Download and install from [PostgreSQL website](https://www.postgresql.org/download/windows/)

### 2. Create Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE p2m_database;

# Exit psql
\q
```

### 3. Run Migration

```bash
# Navigate to backend directory
cd backend/minio-backend

# Run migration script
psql -d p2m_database -U your_username -f migrations/001_create_documents_table.sql
```

### 4. Configure Backend

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your PostgreSQL credentials
# Update DATABASE_URL with your actual connection string
nano .env  # or use your preferred editor

# Install dependencies
npm install

# Start backend
node server.js
```

You should see:
```
Backend running on http://localhost:3000
```

### 5. Test the Application

1. Ensure MinIO is running (see main README for MinIO setup)
2. Start the frontend: `cd front-end && npm run dev`
3. Navigate to the Agent AI tab
4. Drag and drop a PDF file
5. You should see the success banner: "✓ TÉLÉCHARGEMENT RÉUSSI"
6. Check your PostgreSQL database to verify the record was created:
   ```bash
   psql -d p2m_database -c "SELECT * FROM documents ORDER BY created_at DESC LIMIT 1;"
   ```

## Troubleshooting

### Connection Errors

**Error: "role does not exist"**
```bash
# Create the PostgreSQL user
createuser -U postgres your_username
```

**Error: "database does not exist"**
```bash
# Create the database
createdb -U postgres p2m_database
```

**Error: "password authentication failed"**
- Check your DATABASE_URL or PGPASSWORD in `.env`
- Verify PostgreSQL pg_hba.conf allows password authentication
- Try connecting manually: `psql -d p2m_database -U your_username`

### Migration Errors

**Error: "extension uuid-ossp does not exist"**
```bash
# Connect as superuser and create extension
psql -d p2m_database -U postgres
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

## Benefits of This Migration

1. **Simpler Setup**: No need for external Supabase account
2. **Full Control**: Direct access to your local PostgreSQL database
3. **Better Performance**: No network latency to external service
4. **Privacy**: All data stays on your local machine
5. **Cost**: Free - no Supabase subscription needed
6. **Security**: Added rate limiting to prevent abuse

## Security Note

The rate limiter is configured to allow 10 uploads per 15 minutes per IP address. You can adjust this in `server.js` if needed:

```javascript
const uploadLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 10, // Adjust this number as needed
  message: { error: "Too many upload requests, please try again later." },
});
```

## Rollback (If Needed)

If you need to rollback to Supabase:

```bash
git checkout b02cf96  # Last commit before PostgreSQL migration
```

However, note that rolling back will lose the success banner enhancement.
