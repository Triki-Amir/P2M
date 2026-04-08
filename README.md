# P2M - Arborescence du projet

Cette arborescence est generee automatiquement a partir des fichiers suivis par Git.

```text
P2M/
├── app/
│   ├── migrations/
│   │   ├── versions/
│   │   │   ├── 0001_initial.py
│   │   │   ├── 0002_add_processing_notes_column.py
│   │   │   └── 0003_remove_proceccing_note_column.py
│   │   ├── env.py
│   │   ├── README
│   │   └── script.py.mako
│   ├── __init__.py
│   ├── alembic.ini
│   ├── api.py
│   ├── database.py
│   ├── models.py
│   ├── README.md
│   └── start_api.py
├── data/
│   └── o/
├── minio_server/
│   ├── minio-backend/
│   │   ├── migrations/
│   │   │   ├── 001_create_documents_table.sql
│   │   │   └── README.md
│   │   ├── .env.example
│   │   ├── .gitignore
│   │   ├── package.json
│   │   ├── pdfuploader.html
│   │   ├── README.md
│   │   ├── server.js
│   │   └── test-setup.sh
│   └── docker-compose.yml
├── nlp_pipeline_svc/
│   ├── app/
│   │   ├── nlp/
│   │   │   ├── chunker.py
│   │   │   ├── cleaning.py
│   │   │   ├── language_detection.py
│   │   │   └── translation.py
│   │   ├── config.py
│   │   ├── main.py
│   │   └── pipeline.py
│   ├── data/
│   │   ├── nlp_completed.json
│   │   └── ocr_completed.json
│   ├── DETAILS_FONCTIONNEMENT.md
│   ├── README.md
│   ├── requirements.txt
│   └── test_nlp.py
├── ocr_service/
│   ├── .gitignore
│   ├── __init__.py
│   ├── config.py
│   ├── main.py
│   ├── output_writer.py
│   ├── paddle_ocr.py
│   ├── pdf_to_images.py
│   └── requirements.txt
├── postgres_server/
│   └── d/
├── rabbitmq_server/
│   ├── consumers/
│   │   └── o/
│   ├── Producers/
│   │   ├── ingestion.py
│   │   └── scheduler.py
│   ├── docker-compose.yml
│   ├── start_consumer.py
│   ├── test_consumer.py
│   └── test_producer.py
├── redis_server/
│   └── d/
├── shared/
│   ├── __init__.py
│   ├── event_bus.py
│   └── models.py
├── .env.example
├── .gitignore
├── __init__.py
├── ARCHITECTURE.md
├── IMPLEMENTATION_COMPLETE.md
├── INTEGRATION_TEST_GUIDE.md
├── PR_SUMMARY.md
├── QUICK_START.md
├── run_pipeline.py
├── VERIFICATION_CHECKLIST.md
└── verify_integration.py
```
