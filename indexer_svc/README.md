# P2M — PDF to Meaning Pipeline

An end-to-end document intelligence pipeline that converts Arabic/French/English
PDF tender documents into searchable semantic vectors stored in PostgreSQL with
pgvector.

---

## Architecture Overview

```
┌─────────────┐     ocr_completed.json      ┌─────────────────┐     nlp_completed.json      ┌──────────────────┐
│             │ ─────────────────────────►  │                 │ ─────────────────────────►  │                  │
│ OCR Service │                             │   NLP Service   │                             │ Indexer Service  │
│             │                             │                 │                             │                  │
└─────────────┘                             └─────────────────┘                             └──────────────────┘
      │                                             │                                                │
  pdf → images                               clean, detect,                                  embed + store
  layout detection                           translate, chunk                                in pgvector
  block extraction
```

Services communicate via JSON files in a shared `data/` folder.
RabbitMQ integration is planned for production — the file-based bus is a
development stand-in that uses the same `event_bus.consume/publish` API.

---

## Project Structure

```
P2M/
├── data/                          # Shared event bus folder
│   ├── ocr_completed.json         # OCR service output
│   └── nlp_completed.json         # NLP service output
│
├── shared/
│   ├── models.py                  # Pydantic schemas (OcrDocument, NlpDocument, NlpChunk…)
│   └── event_bus.py               # File-based publish/consume
│
├── ocr_service/                   # PDF → structured blocks
│   └── ...
│
├── nlp_pipeline_svc/
│   └── app/
│       ├── main.py                # Entry point — reads ocr_completed.json
│       ├── pipeline.py            # NlpOrchestrator — orchestrates all steps
│       ├── config.py              # Service settings
│       └── nlp/
│           ├── cleaning.py        # Text normalisation
│           ├── chunker.py         # Block-type-aware chunking
│           ├── language_detection.py  # Marker-based AR/FR/EN detection
│           └── translation.py     # Helsinki-NLP AR→EN, FR→EN
│
├── indexer_svc/
│   └── app/
│       ├── main.py                # Entry point — reads nlp_completed.json
│       ├── config.py              # DB connection, model settings
│       ├── embedder.py            # bge-m3 dense + sparse embedding
│       ├── store.py               # pgvector upsert logic
│       └── schema.sql             # Table + index definitions
│
├── docker-compose.yml             # PostgreSQL + pgvector container
├── requirements.txt
├── run_pipeline.py                # Runs OCR → NLP → Indexer in sequence
└── run_nlp_only.py                # Runs NLP → Indexer without re-running OCR
```

---

## Shared Models (`shared/models.py`)

### `OcrBlock`
One detected layout region from a PDF page.

| Field | Type | Description |
|---|---|---|
| `type` | `str` | `heading \| sub_heading \| paragraph \| table \| table_caption` |
| `text` | `str` | Raw extracted text |
| `bbox` | `float[]` | Bounding box `[x1, y1, x2, y2]` in pixels |
| `section_title` | `str \| None` | Breadcrumb of nearest heading above this block |
| `context` | `str \| None` | Preceding paragraph/caption (tables only) |

### `NlpChunk`
One semantic unit produced by the NLP service — the atom the indexer embeds.

| Field | Type | Description |
|---|---|---|
| `chunk_id` | `str` | MD5 of `doc_id:page:block:chunk:text` |
| `block_type` | `str` | Forwarded from `OcrBlock.type` |
| `source_lang` | `str` | `ar \| fr \| en` |
| `text_original` | `str` | Cleaned text in source language |
| `text_en` | `str` | English translation (embedded) |
| `metadata` | `dict` | `section_title`, `context`, `translation_failed` |
| `bbox` | `float[] \| None` | Bounding box from OCR |

---

## Service 1 — OCR Service

Converts a PDF into an `OcrDocument` of typed, structured blocks using layout
detection. Publishes `ocr_completed.json`.

Not detailed here — see `ocr_service/`.

---

## Service 2 — NLP Pipeline (`nlp_pipeline_svc`)

### What it does

For every `OcrBlock` in the `OcrDocument`:

```
1. Clean text          cleaning.py        normalise whitespace, strip noise
2. Detect language     language_detection.py  AR → FR → EN (marker-based)
3. Translate to EN     translation.py     Helsinki-NLP opus-mt models
4. Chunk               chunker.py         strategy depends on block type
5. Build NlpChunk      pipeline.py        with metadata promoted from OcrBlock
```

After all blocks: compute document-level `source_lang` via majority vote.

### Language Detection (`language_detection.py`)

Purely marker-based — no external statistical library needed.

```
Detection order (first match wins):
  1. Any character in Unicode range U+0600–U+06FF  → "ar"
     (covers single Arabic words like "ملحق", "ملاحظة:")
  2. French function word present in text          → "fr"
     (le, la, les, un, une, est, sont, avec, …)
  3. Default                                        → "en"
```

This approach is more reliable than `langdetect` for the short blocks
typical in legal/tender documents.

### Translation (`translation.py`)

Uses Helsinki-NLP MarianMT models loaded locally:
- Arabic → English: `Helsinki-NLP/opus-mt-ar-en`
- French → English: `Helsinki-NLP/opus-mt-fr-en`
- English: passthrough (no translation)

Translation is applied to the **whole block** before chunking so the chunker
always operates on coherent English text.

### Chunking (`chunker.py`)

Block type determines the strategy — no single approach fits all content:

| `block.type` | Strategy | Rationale |
|---|---|---|
| `heading` | **Atomic** | A title is indivisible |
| `sub_heading` | **Atomic** | A sub-title is indivisible |
| `table` | **Atomic** | Row/column structure must stay intact |
| `table_caption` | **Atomic** | Short, must be retrieved whole |
| `paragraph` (list pattern) | **List** | Bullet items need their siblings |
| `paragraph` (prose) | **Sentence-boundary** | Split at sentence endings + char ceiling |

**Atomic chunking** — returns the entire block as exactly one chunk.
No library. Pure Python string operation.

**List detection** — regex scans line prefixes. If ≥ 45 % of non-blank
lines start with `- `, `•`, `1.`, `a)`, `(i)` etc. the block is a list.

**Sentence-boundary chunking** — splits on `.`, `!`, `?`, `؟` then packs
sentences greedily until `max_chunk_chars` is reached. A hard ceiling
re-splits any segment that exceeds the limit.

> **Why no embedding model inside the chunker?**
> Embeddings are computed in the indexer after chunking. Running them in
> the chunker too would double the compute cost and load a large model in
> the wrong service.

### Configuration (`nlp_pipeline_svc/app/config.py`)

| Key | Default | Description |
|---|---|---|
| `MAX_CHUNK_CHARS` | `1200` | Hard character ceiling per chunk |
| `CHUNK_OVERLAP` | `100` | Char overlap when hard-splitting |
| `MIN_SENTENCES` | `3` | Min sentences before a paragraph split |
| `SIMILARITY_THRESHOLD` | `0.75` | (Reserved for future semantic chunking) |

---

## Service 3 — Indexer (`indexer_svc`)

### What it does

```
1. Load nlp_completed.json
2. Embed every chunk with bge-m3  → dense vector (1024-dim)
                                   + sparse vector (250002-dim)
3. Upsert into PostgreSQL / pgvector
```

### Embedding Model — `BAAI/bge-m3`

bge-m3 is a hybrid multilingual model that produces two complementary
representations per text:

**Dense vector (1024 dimensions)**
A single float vector encoding overall semantic meaning. Texts with
similar meaning are geometrically close regardless of language.
Used for semantic / conceptual search.

**Sparse vector (lexical weights)**
A weighted bag-of-words over the model's 250,002-token vocabulary.
Non-zero weights only for tokens actually present in the text.
Used for exact keyword / terminology matching.

**Why hybrid?**
- Dense alone misses exact terminology (article numbers, legal codes,
  proper nouns like "المقسم عدد 14")
- Sparse alone misses paraphrase and cross-lingual matches
- Combined via Reciprocal Rank Fusion (RRF) at query time, both
  weaknesses are covered

### Database Schema (`schema.sql`)

```sql
chunks (
    chunk_id        TEXT PRIMARY KEY,
    doc_id          TEXT,
    page_index      INT,
    block_index     INT,
    chunk_index     INT,
    block_type      TEXT,
    source_lang     TEXT,
    text_original   TEXT,       -- source language
    text_en         TEXT,       -- English, what was embedded
    section_title   TEXT,       -- from OcrBlock.section_title
    context         TEXT,       -- from OcrBlock.context
    translation_failed BOOLEAN,
    bbox            FLOAT[],
    dense_vec       vector(1024),
    sparse_vec      sparsevec(250002),
    indexed_at      TIMESTAMPTZ
)
```

**Indexes:**
- `HNSW` on `dense_vec` with `vector_ip_ops` (inner product — equivalent
  to cosine on normalised bge-m3 vectors, faster)
- `HNSW` on `sparse_vec` with `sparsevec_ip_ops`
- B-tree indexes on `doc_id`, `block_type`, `source_lang` for filtered search

### Configuration (`indexer_svc/app/config.py`)

| Key | Default | Description |
|---|---|---|
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `p2m_db` | Database name |
| `DB_USER` | `p2m` | Database user |
| `DB_PASSWORD` | `p2m_secret` | Database password |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | HuggingFace model ID |
| `EMBED_BATCH_SIZE` | `16` | Chunks per forward pass (reduce if OOM) |

---

## Setup & Running

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Start PostgreSQL + pgvector

```bash
docker-compose up -d
```

The `schema.sql` is mounted as an init script — the table and indexes are
created automatically on first container start.

### 3. Run the full pipeline

```bash
# Full run: OCR → NLP → Indexer
python run_pipeline.py path/to/document.pdf

# NLP + Indexer only (reuse existing ocr_completed.json)
python run_nlp_only.py

# Indexer only (reuse existing nlp_completed.json)
python -m indexer_svc.app.main
```

### 4. Verify data in PostgreSQL

```bash
docker exec -it p2m_pgvector psql -U p2m -d p2m_db

-- Check rows
SELECT doc_id, block_type, source_lang, LEFT(text_en, 60)
FROM chunks
ORDER BY page_index, block_index, chunk_index;

-- Check vector dimensions
SELECT chunk_id, vector_dims(dense_vec) FROM chunks LIMIT 3;
```

---

## Hybrid Search Query (future retrieval service)

At query time, embed the user question with bge-m3 then run:

```sql
-- Dense search
SELECT chunk_id, text_en,
       (dense_vec <#> query_dense_vec) * -1 AS dense_score
FROM chunks
ORDER BY dense_vec <#> query_dense_vec
LIMIT 20;

-- Sparse search
SELECT chunk_id, text_en,
       (sparse_vec <#> query_sparse_vec) * -1 AS sparse_score
FROM chunks
ORDER BY sparse_vec <#> query_sparse_vec
LIMIT 20;

-- Combine with RRF in application layer
-- final_score = 1/(k + dense_rank) + 1/(k + sparse_rank)  where k=60
```

---

## Known Limitations

| Issue | Status |
|---|---|
| Block 3 double-chunk (Helsinki model internal truncation) | Under investigation |
| Translation quality on long legal Arabic sentences | Helsinki-NLP limitation — consider `Helsinki-NLP/opus-mt-tc-big-ar-en` for better quality |
| `section_title` always null | OCR service does not yet populate heading breadcrumbs |
| Footer blocks (block 13) indexed as content | No footer detection in OCR service yet |
| RabbitMQ integration | Planned — event_bus.py API is already compatible |
