# P2M - Arborescence du projet
### Vue d'ensemble (Graphe de la Pipeline)

```mermaid
graph TD
    classDef frontend fill:#f3f4f6,stroke:#333,stroke-width:2px;
    classDef api fill:#dbeafe,stroke:#2563eb,stroke-width:2px;
    classDef queue fill:#fef3c7,stroke:#d97706,stroke-width:2px;
    classDef worker fill:#dcfce7,stroke:#16a34a,stroke-width:2px;
    classDef storage fill:#fee2e2,stroke:#dc2626,stroke-width:2px;
    classDef smart fill:#f3e8ff,stroke:#9333ea,stroke-width:2px;

    UI[React / Vite]:::frontend -->|Upload| API[FastAPI Upload API]:::api
    UI -. Websocket .-> RAG[RAG Service - Ollama]:::smart

    API -->|1. Object Storage| MinIO[(MinIO)]:::storage
    API -->|2. init processing| PG[(PostgreSQL)]:::storage
    API -->|3. document_uploaded| Q1([ocr_queue]):::queue

    Q1 -->|Consume| OCR[OCR Service / Paddle]:::worker
    OCR -. Fetch PDF .-> MinIO
    OCR -->|4. ocr_completed| Q2([nlp_queue]):::queue

    Q2 -->|Consume| NLP1[1. Meta Extractor Regex/LLM]:::worker
    NLP1 --> NLP2[2. Translation]:::worker
    NLP2 --> NLP3[3. Semantic Chunker]:::worker
    NLP3 -->|5. nlp_completed| Q3([indexer_queue]):::queue

    Q3 -->|Consume| IDX[Indexer Service]:::worker
    IDX -->|6. Upsert Vectors| PGV[(pgvector)]:::storage
    IDX -. Update Status SUCCESS .-> PG

    RAG -. Retriever: Semantic+BM25 .-> PGV
    COMP[Compliance Service]:::smart -. Match Rules .-> PGV
    
```

---
Cette arborescence annotée décrit chaque composant du projet pour faciliter la compréhension globale de l'architecture par un modèle d'IA ou un nouveau développeur.

```text
P2M/
├── app/                              # Application API backend principale gérant la logique métier et la BDD
│   ├── migrations/                   # Scripts de migration de base de données (Alembic)
│   ├── api.py                        # Définition des endpoints REST de l'API principale
│   ├── database.py                   # Configuration de la connexion à la base de données PostgreSQL
│   ├── models.py                     # Définition des modèles de données (ORM SQLAlchemy)
│   └── start_api.py                  # Script de démarrage du serveur API backend
├── front-end/                        # Interface utilisateur web
│   ├── src/                          # Code source React/TypeScript de l'application front-end
│   ├── package.json                  # Dépendances et scripts de build du front-end
│   └── vite.config.ts                # Configuration du bundler Vite pour le front-end
├── indexer_svc/                      # Microservice d'indexation vectorielle des documents
│   ├── app/embedder.py               # Génération des embeddings vectoriels depuis le texte
│   ├── app/main.py                   # Point d'entrée de l'API du service d'indexation
│   └── app/store.py                  # Logique d'insertion des vecteurs dans PostgreSQL/pgvector
├── minio_server/                     # Configuration du stockage d'objets (documents bruts)
│   ├── minio-backend/server.js       # Serveur Node.js gérant les uploads de PDF vers MinIO
│   └── docker-compose.yml            # Description du conteneur MinIO
├── nlp_pipeline_svc/                 # Microservice de traitement du langage naturel (NLP)
│   ├── app/nlp/chunker.py            # Découpage du texte en segments pour l'indexation RAG
│   ├── app/nlp/cleaning.py           # Nettoyage et normalisation des textes extraits
│   └── app/pipeline.py               # Orchestration des étapes de transformation NLP
├── ocr_service/                      # Microservice d'extraction de texte (OCR) depuis les PDFs
│   ├── paddle_ocr.py                 # Implémentation du moteur OCR via PaddleOCR
│   ├── pdf_to_images.py              # Conversion des pages PDF en images pour traitement OCR
│   └── main.py                       # Point d'entrée de l'API / worker de l'OCR
├── postgres_server/                  # Base de données relationnelle et vectorielle (pgvector)
│   ├── init/                         # Scripts SQL d'initialisation des tables et schémas
│   └── docker-compose.yml            # Description du conteneur PostgreSQL
├── rabbitmq_server/                  # Courtier de messages pour l'architecture événementielle
│   ├── consumers/ocr_services.py     # Worker consommant les tâches OCR depuis la file d'attente
│   └── Producers/ingestion.py        # Envoie des événements d'ingestion de nouveaux documents
├── rag_service/                      # Microservice RAG (Retrieval-Augmented Generation) pour le chat
│   ├── retriever.py                  # Recherche sémantique de contexte dans la BDD vectorielle
│   ├── generator.py                  # Génération de réponses IA avec le LLM basé sur le contexte
│   ├── websocket_handler.py          # Gestion des connexions WebSocket pour le chat en temps réel
│   └── start_rag.py                  # Point d'entrée du service RAG
├── redis_server/                     # Base de données en mémoire pour le cache et les sessions
├── shared/                           # Code commun partagé entre les différents microservices Python
│   ├── event_bus.py                  # Abstraction de la communication asynchrone via RabbitMQ
│   └── models.py                     # Modèles Pydantic partagés (contrats d'interfaces)
├── ARCHITECTURE.md                   # Documentation détaillée sur l'architecture globale
├── QUICK_START.md                    # Guide rapide pour l'installation, le build et le lancement
└── run_pipeline.py                   # Script global d'exécution complète d'un pipeline de test
```
