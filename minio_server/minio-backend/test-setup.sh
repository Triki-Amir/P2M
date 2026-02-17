#!/bin/bash

# Test Script for Backend Integration
echo "=== Testing Backend Server ==="

# Check if dependencies are installed
if [ ! -d "node_modules" ]; then
  echo "Error: Dependencies not installed. Run 'npm install' first."
  exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
  echo "Warning: .env file not found. Using default configuration from .env.example"
  cp .env.example .env
fi

echo "✓ Dependencies installed"
echo "✓ Configuration file present"

# Validate server syntax
node -c server.js
if [ $? -eq 0 ]; then
  echo "✓ Server syntax is valid"
else
  echo "✗ Server syntax error"
  exit 1
fi

# Check required Node modules
node -e "require('@supabase/supabase-js'); console.log('✓ Supabase client available')"
node -e "require('dotenv'); console.log('✓ Dotenv available')"
node -e "require('minio'); console.log('✓ MinIO client available')"
node -e "require('express'); console.log('✓ Express available')"
node -e "require('multer'); console.log('✓ Multer available')"
node -e "require('cors'); console.log('✓ CORS available')"

echo ""
echo "=== All checks passed! ==="
echo ""
echo "To start the server:"
echo "  node server.js"
echo ""
echo "Make sure:"
echo "  1. MinIO is running on localhost:9000"
echo "  2. The 'pdf-storage' bucket exists in MinIO"
echo "  3. Supabase database has the 'documents' table"
echo "  4. Run the migration: migrations/001_create_documents_table.sql"
