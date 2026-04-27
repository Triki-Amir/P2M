#!/usr/bin/env python
"""
Start the FastAPI backend server for document uploads.
"""
import sys
import os
import uvicorn

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

if __name__ == "__main__":
    api_port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(
        "ingestion_service.api:app",
        host="0.0.0.0",
        port=api_port,
        reload=True,
        log_level="info"
    )
