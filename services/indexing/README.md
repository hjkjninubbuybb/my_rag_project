# Indexing Service

Document indexing and retrieval service for the RAG system.

## Features

- Document parsing (PDF, DOCX)
- Text cleaning (PolicyCleaner, ManualCleaner)
- Multiple chunking strategies (fixed, recursive, sentence, semantic, multimodal)
- Embedding generation (DashScope text-embedding-v4)
- Sparse vector generation (jieba BM25)
- Vector storage (Qdrant)
- Parent node storage (MySQL)
- File storage (MinIO)
- Hybrid retrieval (dense + sparse)
- Reranking (DashScope gte-rerank)
- Role-based access control

## API Endpoints

- `POST /api/v1/index` - Index document from MinIO
- `POST /api/v1/retrieve` - Retrieve relevant documents
- `GET /api/v1/collections` - List all collections
- `GET /api/v1/collections/{name}/files` - List files in collection
- `DELETE /api/v1/collections/{name}` - Delete collection
- `DELETE /api/v1/documents/{collection}/{filename}` - Delete document
- `GET /health` - Health check

## Environment Variables

```bash
# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_PATH=data/vectordb

# MySQL
MYSQL_URL=mysql+pymysql://rag_user:rag_password@localhost:3306/rag_db
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=rag_user
MYSQL_PASSWORD=rag_password
MYSQL_DATABASE=rag_db

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=false

# DashScope
DASHSCOPE_API_KEY=your_api_key_here
```

## Installation

```bash
# Install dependencies
poetry install

# Run service
poetry run python -m app.main
```

## Docker

```bash
# Build image
docker build -t indexing-service:latest .

# Run container
docker run -p 8001:8001 \
  -e QDRANT_URL=http://qdrant:6333 \
  -e MYSQL_URL=mysql+pymysql://rag_user:rag_password@mysql:3306/rag_db \
  -e MINIO_ENDPOINT=minio:9000 \
  -e DASHSCOPE_API_KEY=your_key \
  indexing-service:latest
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Indexing Service                      │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Parsing    │  │   Chunking   │  │  Embedding   │ │
│  │              │  │              │  │              │ │
│  │ - PyMuPDF    │  │ - Fixed      │  │ - DashScope  │ │
│  │ - pypdf      │  │ - Recursive  │  │ - Jieba      │ │
│  │ - docx2txt   │  │ - Sentence   │  │   (sparse)   │ │
│  │              │  │ - Semantic   │  │              │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Storage    │  │  Retrieval   │  │   Reranking  │ │
│  │              │  │              │  │              │ │
│  │ - Qdrant     │  │ - Dense      │  │ - DashScope  │ │
│  │ - MySQL      │  │ - Sparse     │  │   gte-rerank │ │
│  │ - MinIO      │  │ - Hybrid     │  │              │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Dependencies

- Python 3.10+
- numpy >= 2.0 (required by MinerU)
- FastAPI
- LlamaIndex
- Qdrant
- MySQL
- MinIO
- DashScope API

## Notes

- This service uses numpy >= 2.0 (different from Agent Service which uses numpy < 2.0)
- VLM image summarization will be implemented in Phase 3 (requires Agent Service)
- All file storage is handled by MinIO (no local file storage)
- Parent nodes (with full images) are stored in MySQL
- Child nodes (with summaries) are stored in Qdrant
