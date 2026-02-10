# Quick Start Guide - Agent AI PDF Upload with Database

This guide will help you get the Agent AI PDF upload feature running in under 10 minutes.

## Prerequisites

1. **Node.js** (v14 or higher) - [Download here](https://nodejs.org/)
2. **MinIO** - Running on localhost:9000
3. **Supabase account** - Already configured in the project

## Step 1: Setup MinIO (5 minutes)

### Option A: Using Docker (Recommended)

```bash
docker run -d \
  -p 9000:9000 \
  -p 9001:9001 \
  --name minio \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=minioadmin" \
  minio/minio server /data --console-address ":9001"
```

### Option B: Download and Run

1. Download MinIO: https://min.io/download
2. Run: `./minio server /data --console-address ":9001"`

### Create the Bucket

1. Open http://localhost:9001
2. Login with: `minioadmin` / `minioadmin`
3. Click "Create Bucket"
4. Name: `pdf-storage`
5. Click "Create"

## Step 2: Setup Database (2 minutes)

1. Open your Supabase project: https://supabase.com/dashboard
2. Go to **SQL Editor**
3. Copy and paste this file content: `backend/minio-backend/migrations/001_create_documents_table.sql`
4. Click **Run**
5. Verify table created: Go to **Table Editor** → You should see `documents` table

## Step 3: Setup Backend (2 minutes)

```bash
# Navigate to backend directory
cd backend/minio-backend

# Install dependencies
npm install

# Configure environment (already done, .env exists)
# If not, copy: cp .env.example .env

# Start the server
node server.js
```

You should see:
```
Backend running on http://localhost:3000
```

**Keep this terminal open!**

## Step 4: Setup Frontend (2 minutes)

Open a **new terminal**:

```bash
# Navigate to frontend directory
cd front-end

# Install dependencies (if not already done)
npm install

# Start development server
npm run dev
```

You should see the Vite dev server URL (usually http://localhost:5173)

## Step 5: Test the Feature (1 minute)

1. Open your browser to the frontend URL
2. Navigate to the **Agent AI** tab
3. Drag and drop a PDF file into the upload area
4. Wait for the processing
5. You should see a success message with:
   - Document ID
   - Storage path

## Verification

### Check MinIO
- Go to http://localhost:9001
- Look in the `pdf-storage` bucket
- Your file should be there!

### Check Database
- Go to Supabase → Table Editor → documents
- You should see a new row with your file's metadata

## Troubleshooting

### Backend won't start

**Error: "SUPABASE_URL and SUPABASE_KEY environment variables are required"**
- Solution: Check that `.env` file exists in `backend/minio-backend/`
- If not, copy from `.env.example`: `cp .env.example .env`

**Error: "ECONNREFUSED localhost:9000"**
- Solution: MinIO is not running. Start MinIO (see Step 1)

**Error: "Bucket does not exist"**
- Solution: Create the `pdf-storage` bucket in MinIO (see Step 1)

### Frontend errors

**Error: "Failed to fetch"**
- Solution: Backend is not running. Start it (see Step 3)

**Error: "CORS error"**
- Solution: Make sure backend is running and CORS is enabled (it is by default)

### Upload fails

**Error: "Only PDF files allowed"**
- Solution: You tried to upload a non-PDF file. Use a PDF file.

**Error: "Failed to save document metadata"**
- Solution: Database migration not applied. Run the SQL migration (see Step 2)

## Default Configuration

The system uses these defaults (from `.env`):

```
MinIO Endpoint: localhost:9000
MinIO Credentials: minioadmin / minioadmin
Backend Port: 3000
Database: Supabase (configured)
```

## Next Steps

### For Development
- Frontend runs on: http://localhost:5173 (Vite default)
- Backend API on: http://localhost:3000
- MinIO Console: http://localhost:9001

### For Production
1. Update `.env` with production credentials
2. Set proper CORS restrictions in `server.js`
3. Use production MinIO instance
4. Enable HTTPS
5. Set up proper backup for database

## Need Help?

- Check `IMPLEMENTATION_SUMMARY.md` for detailed documentation
- Check `VERIFICATION_CHECKLIST.md` for comprehensive testing
- Review backend logs in the terminal
- Check browser console for frontend errors

## Clean Up

To stop everything:

1. Press `Ctrl+C` in the backend terminal
2. Press `Ctrl+C` in the frontend terminal
3. Stop MinIO: `docker stop minio` (if using Docker)

To completely remove:
```bash
docker rm minio  # Remove MinIO container
rm -rf node_modules  # Remove dependencies
```

---
# Minio Activate server
minio.exe server C:\MinIO\data


**Happy coding! 🚀**
