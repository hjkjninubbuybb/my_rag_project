# Indexing Service Implementation Summary

## Overview

Successfully implemented the Indexing Service (Phase 2 of the refactoring plan) by merging ingestion, retrieval, and shared library functionality into a consolidated service.

## Directory Structure

```
services/indexing/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI application with lifespan
│   ├── config.py                  # Service settings
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py              # 8 API endpoints
│   ├── core/
│   │   ├── __init__.py
│   │   ├── types.py               # ABCs (migrated from shared)
│   │   └── registry.py            # ComponentRegistry (migrated from shared)
│   ├── config/
│   │   ├── __init__.py
│   │   └── experiment.py          # ExperimentConfig (migrated from shared)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ingestion.py           # Ingestion logic (migrated + updated)
│   │   ├── retrieval.py           # Retrieval logic (migrated from inference)
│   │   └── multimodal_retrieval.py # Multimodal retrieval (migrated from inference)
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── vectordb.py            # Qdrant manager (migrated + updated)
│   │   ├── mysql_client.py        # MySQL client (NEW)
│   │   └── minio_client.py        # MinIO client (NEW)
│   ├── components/
│   │   ├── __init__.py
│   │   ├── chunkers/              # All chunkers (migrated)
│   │   │   ├── fixed.py
│   │   │   ├── recursive.py
│   │   │   ├── sentence.py
│   │   │   ├── semantic.py
│   │   │   └── multimodal.py
│   │   ├── providers/             # All providers (migrated)
│   │   │   ├── dashscope.py
│   │   │   ├── bgem3.py           # Jieba sparse vectors
│   │   │   └── vlm.py
│   │   └── processors/            # Image processor (migrated)
│   │       └── image.py
│   ├── parsing/
│   │   ├── __init__.py
│   │   ├── parser.py              # Document parser (migrated)
│   │   ├── multimodal_parser.py   # PDF image extraction (migrated)
│   │   └── cleaner.py             # PolicyCleaner/ManualCleaner (migrated)
│   └── utils/
│       ├── __init__.py
│       ├── logger.py              # Loguru logger (migrated from shared)
│       └── role_mapper.py         # Role extraction (migrated from shared)
├── pyproject.toml                 # Poetry dependencies (numpy>=2.0)
├── Dockerfile                     # Multi-stage build
├── README.md                      # Service documentation
├── .gitignore
└── .env.example

```

## API Endpoints (8 total)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/index` | POST | Index document from MinIO |
| `/api/v1/retrieve` | POST | Retrieve relevant documents |
| `/api/v1/collections` | GET | List all collections |
| `/api/v1/collections/{name}/files` | GET | List files in collection |
| `/api/v1/collections/{name}` | DELETE | Delete collection |
| `/api/v1/documents/{collection}/{filename}` | DELETE | Delete document |
| `/health` | GET | Health check |
| `/` | GET | Root endpoint |

## Key Features

### 1. Storage Clients

- **VectorStoreManager**: Qdrant vector database (dual-mode: URL/local path)
- **MySQLClient**: Parent nodes, collections, documents metadata
- **MinIOClient**: File storage (raw-documents, extracted-images buckets)

### 2. Document Processing

- **Parsing**: PDF (PyMuPDF, pypdf), DOCX (docx2txt)
- **Cleaning**: PolicyCleaner, ManualCleaner
- **Chunking**: Fixed, Recursive, Sentence, Semantic, Multimodal
- **Embedding**: DashScope text-embedding-v4 (1536-dim)
- **Sparse Vectors**: Jieba BM25 (~15MB, replaces BGE-M3 ~2GB)

### 3. Retrieval

- Dense retrieval (text embeddings)
- Sparse retrieval (jieba BM25)
- Hybrid retrieval (dense + sparse)
- Reranking (DashScope gte-rerank)
- Role-based filtering

### 4. Multimodal Support

- Image extraction from PDFs
- Parent-child node hierarchy
- MySQL storage for parent nodes (full images)
- Qdrant storage for child nodes (summaries)
- VLM integration (Phase 3 - to be implemented)

## Migration Summary

### From `shared/rag_shared/`

- ✅ `core/types.py` → `app/core/types.py`
- ✅ `core/registry.py` → `app/core/registry.py`
- ✅ `config/experiment.py` → `app/config/experiment.py`
- ✅ `utils/logger.py` → `app/utils/logger.py`
- ✅ `utils/role_mapper.py` → `app/utils/role_mapper.py`

### From `services/ingestion/`

- ✅ All chunkers (fixed, recursive, sentence, semantic, multimodal)
- ✅ All providers (dashscope, bgem3, vlm)
- ✅ All processors (image)
- ✅ All parsing modules (parser, multimodal_parser, cleaner)
- ✅ Ingestion service (updated for new API)
- ✅ VectorStoreManager (updated for config-free API)

### From `services/inference/`

- ✅ RetrievalService
- ✅ MultimodalRetrievalService

### New Implementations

- ✅ MySQLClient (parent_nodes, collections, documents tables)
- ✅ MinIOClient (file upload/download, presigned URLs)
- ✅ API routes (8 endpoints)
- ✅ FastAPI main application with lifespan
- ✅ Service configuration (ServiceSettings)

## Import Updates

All imports updated from `rag_shared.*` to `app.*`:
- ✅ 10 files updated with sed
- ✅ No remaining `rag_shared` imports

## Dependencies (pyproject.toml)

Key dependencies:
- Python 3.10+
- **numpy >= 2.0** (required by MinerU, different from Agent Service)
- FastAPI, Uvicorn
- LlamaIndex (core, embeddings, llms)
- PyMuPDF, pypdf, python-docx, Pillow
- jieba (Chinese NLP)
- Qdrant client
- MinIO
- PyMySQL, SQLAlchemy
- httpx (for calling Agent VLM API in Phase 3)
- loguru

## Docker Support

- Multi-stage build (builder + runtime)
- Health check endpoint
- Environment variable configuration
- Port 8001 exposed

## Environment Variables

Required:
- `QDRANT_URL` or `QDRANT_PATH`
- `MYSQL_URL` (or individual MySQL_* vars)
- `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`
- `DASHSCOPE_API_KEY`

## Notes

1. **VLM Integration**: Image summarization will be implemented in Phase 3 when Agent Service is ready. Currently commented out in ingestion flow.

2. **numpy Conflict**: This service uses numpy>=2.0 (MinerU requirement), while Agent Service will use numpy<2.0 (LangChain requirement). Independent Poetry environments resolve this.

3. **No Local Storage**: All files stored in MinIO, no local file system usage.

4. **Backward Compatibility**: VectorStoreManager keeps old methods for compatibility with existing code, adds new config-free methods for API routes.

5. **MySQL Schema**: Tables created automatically via SQLAlchemy ORM (parent_nodes, collections, documents).

## Testing

To test the service:

```bash
# Install dependencies
cd services/indexing
poetry install

# Run service
poetry run python -m app.main

# Test health endpoint
curl http://localhost:8001/health

# Test API docs
open http://localhost:8001/docs
```

## Next Steps (Phase 3)

1. Implement Agent Service (LangGraph + VLM)
2. Enable VLM image summarization in ingestion flow
3. Implement Orchestrator Service
4. Implement Testing Service
5. Update docker-compose.yml
6. Delete old services (gateway, cli, shared)

## Status

✅ Phase 2 Complete - Indexing Service fully implemented and ready for testing.
