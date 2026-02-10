const express = require("express");
const multer = require("multer");
const Minio = require("minio");
const cors = require("cors");

const app = express();
app.use(cors());

// Store files in memory before sending to MinIO
const upload = multer({
  limits: { fileSize: 10 * 1024 * 1024 }, // 10MB
});

// MinIO client
const minioClient = new Minio.Client({
  endPoint: "localhost",
  port: 9000,
  useSSL: false,
  accessKey: "minioadmin",
  secretKey: "minioadmin",
});

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

    await minioClient.putObject(
      "pdf-storage",
      fileName,
      req.file.buffer,
      req.file.size,
      { "Content-Type": "application/pdf" }
    );

    res.json({
      message: "PDF uploaded successfully",
      fileName,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Upload failed" });
  }
});

app.listen(3000, () => {
  console.log("Backend running on http://localhost:3000");
});
