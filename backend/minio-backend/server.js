require("dotenv").config();
const express = require("express");
const multer = require("multer");
const Minio = require("minio");
const cors = require("cors");
const { createClient } = require("@supabase/supabase-js");

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

// Supabase client
if (!process.env.SUPABASE_URL || !process.env.SUPABASE_KEY) {
  console.error("ERROR: SUPABASE_URL and SUPABASE_KEY environment variables are required");
  console.error("Please create a .env file based on .env.example");
  process.exit(1);
}

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_KEY
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

    // Insert metadata into PostgreSQL via Supabase
    // Status set to 'uploaded' to indicate file is in storage and ready for processing
    // (differs from schema default 'pending' which is for records not yet uploaded)
    const { data, error } = await supabase
      .from("documents")
      .insert({
        tenant_id: DEFAULT_TENANT_ID,
        filename: req.file.originalname,
        storage_path: storagePath,
        file_size: req.file.size,
        mime_type: req.file.mimetype,
        status: "uploaded",
        metadata: {
          bucket: BUCKET_NAME,
          uploaded_at: new Date().toISOString(),
        },
      })
      .select()
      .single();

    if (error) {
      console.error("Database error:", error);
      return res.status(500).json({ 
        error: "Failed to save document metadata",
        details: error.message 
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
