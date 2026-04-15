# P2M - Arborescence du projet
### Vue d'ensemble (Graphe de la Pipeline)

```mermaid
graph TD
    %% Configuration du Thème (Design dynamique)
    classDef client fill:#3b82f6,stroke:#1e3a8a,stroke-width:2px,color:#fff,rx:8px,ry:8px,shadow:shadow;
    classDef api fill:#8b5cf6,stroke:#581c87,stroke-width:2px,color:#fff,rx:5px,ry:5px;
    classDef mq fill:#f59e0b,stroke:#b45309,stroke-width:3px,color:#fff,stroke-dasharray: 5 5;
    classDef microservice fill:#10b981,stroke:#065f46,stroke-width:2px,color:#fff,rx:10px,ry:10px;
    classDef db fill:#ef4444,stroke:#7f1d1d,stroke-width:2px,color:#fff,rx:15px,ry:15px;
    classDef ai fill:#ec4899,stroke:#701a75,stroke-width:2px,color:#fff,rx:10px,ry:10px;

    %% Entités
    subgraph Frontend ["🟢 Interface Utilisateur"]
        UI[💻 Frontend (React/Vite)]:::client
    end

    subgraph EntryPoint ["🔵 Couche d'Entrée & Auth"]
        API[🚀 FastAPI (Upload & Auth)]:::api
    end

    subgraph EventBus ["🟠 Message Broker (RabbitMQ)"]
        Q1((ocr_queue)):::mq
        Q2((nlp_queue)):::mq
        Q3((indexer_queue)):::mq
    end

    subgraph Pipeline ["🟢 Document Processing Pipeline"]
        OCR[👁️ OCR Service (PaddleOCR)]:::microservice
        
        subgraph NLP ["🧠 NLP Service (Hybride)"]
            M[Metadata LLM/Regex] 
            T[Translation] 
            C[Semantic Chunker]
            M -.-> T -.-> C
        end
        class M,T,C microservice
        
        IDX[⚙️ Indexer Service]:::microservice
    end

    subgraph Databases ["🔴 Persistance des Données"]
        MinIO[(📦 MinIO: PDF Storage)]:::db
        PG[(🗄️ PostgreSQL: Users)]:::db
        PGV[(📊 pgvector: Chunks)]:::db
    end

    subgraph SmartLayer ["🟣 Couche Intelligente (Smart Layer)"]
        COMP[✅ Compliance Service]:::ai
        RAG[🤖 RAG Service (Ollama)]:::ai
    end

    %% Relations (Cheminement du document)
    UI == 1. Upload PDF ==> API
    UI <== 💬 WebSocket Chat ==> RAG

    API == "2. Save PDF" ==> MinIO
    API == "3. Metadata" ==> PG
    API == "4. Publisher" ==> Q1

    Q1 -. "Consume" .-> OCR
    OCR -. "Read PDF" .-> MinIO
    OCR == "5. ocr_completed" ==> Q2

    Q2 -. "Consume" .-> M
    C == "6. nlp_completed" ==> Q3

    Q3 -. "Consume" .-> IDX
    IDX == "7. Upsert Tensors" ==> PGV
    IDX -. "Update Status" .-> PG

    %% IA Operations
    RAG -. "Semantic/BM25 Search" .-> PGV
    COMP -. "Rule Matching" .-> PGV
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
