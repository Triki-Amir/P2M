require("dotenv").config();
const express = require("express");
const multer = require("multer");
const Minio = require("minio");
const cors = require("cors");
const { Pool } = require("pg");

const app = express();
app.use(cors());

// Store files in memory before sending to MinIO
const upload = multer({
  limits: { fileSize: 10 * 1024 * 1024 }, // 10MB
});

// MinIO client
const minioClient = new Minio.Client({
  endPoint: process.env.MINIO_ENDPOINT || "localhost",
  port: parseInt(process.env.MINIO_PORT) || 9000,
  useSSL: process.env.MINIO_USE_SSL === "true",
  accessKey: process.env.MINIO_ACCESS_KEY || "minioadmin",
  secretKey: process.env.MINIO_SECRET_KEY || "minioadmin",
});

// PostgreSQL client
if (!process.env.DATABASE_URL && !process.env.PGHOST) {
  console.error("ERROR: DATABASE_URL or PostgreSQL connection parameters are required");
  console.error("Please create a .env file based on .env.example");
  process.exit(1);
}

// Pool configuration: DATABASE_URL takes precedence over individual parameters if both are provided
const pool = new Pool(
  process.env.DATABASE_URL
    ? { connectionString: process.env.DATABASE_URL }
    : {
        host: process.env.PGHOST,
        port: process.env.PGPORT || 5432,
        database: process.env.PGDATABASE,
        user: process.env.PGUSER,
        password: process.env.PGPASSWORD,
      }
);

const BUCKET_NAME = process.env.MINIO_BUCKET || "pdf-storage";
const DEFAULT_TENANT_ID = process.env.DEFAULT_TENANT_ID || "00000000-0000-0000-0000-000000000000";

// Upload endpoint
app.post("/upload", upload.single("file"), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ error: "No file uploaded" });
    }

    if (req.file.mimetype !== "application/pdf") {
      return res.status(400).json({ error: "Only PDF files allowed" });
    }

    const fileName = `${Date.now()}-${req.file.originalname}`;
    const storagePath = fileName;

    // Upload to MinIO
    await minioClient.putObject(
      BUCKET_NAME,
      fileName,
      req.file.buffer,
      req.file.size,
      { "Content-Type": "application/pdf" }
    );

    // Insert metadata into PostgreSQL
    // Status set to 'uploaded' to indicate file is in storage and ready for processing
    // (differs from schema default 'pending' which is for records not yet uploaded)
    const query = `
      INSERT INTO documents (tenant_id, filename, storage_path, file_size, mime_type, status, metadata)
      VALUES ($1, $2, $3, $4, $5, $6, $7)
      RETURNING id, tenant_id, filename, storage_path, file_size, mime_type, status, metadata, created_at
    `;
    
    const values = [
      DEFAULT_TENANT_ID,
      req.file.originalname,
      storagePath,
      req.file.size,
      req.file.mimetype,
      'uploaded',
      JSON.stringify({
        bucket: BUCKET_NAME,
        uploaded_at: new Date().toISOString(),
      })
    ];

    const result = await pool.query(query, values);
    const data = result.rows[0];

    if (!data) {
      console.error("Database error: No data returned");
      return res.status(500).json({ 
        error: "Failed to save document metadata",
        details: "No data returned from database" 
      });
    }

    res.json({
      message: "PDF uploaded successfully",
      fileName,
      documentId: data.id,
      storagePath,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Upload failed", details: err.message });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Backend running on http://localhost:${PORT}`);
});
