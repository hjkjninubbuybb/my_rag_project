# Orchestrator Service - Quick Start

Get the Orchestrator Service running in 5 minutes.

## Prerequisites

- Python 3.10+
- Poetry
- Indexing Service running on port 8001
- Agent Service running on port 8002
- MinIO running on port 9000

## Steps

### 1. Install Dependencies

```bash
cd services/orchestrator
poetry install
```

### 2. Configure Environment

```bash
# Copy example config
cp .env.example .env

# For local development, edit .env:
# - Change service URLs to localhost
# - Verify MinIO credentials
```

**Local `.env` example**:
```bash
INDEXING_URL=http://localhost:8001
AGENT_URL=http://localhost:8002
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=false
```

### 3. Start Service

```bash
poetry run python -m app.main
```

Expected output:
```
2024-01-01 10:00:00 | INFO     | Starting Orchestrator Service
2024-01-01 10:00:00 | INFO     | Indexing Service URL: http://localhost:8001
2024-01-01 10:00:00 | INFO     | Agent Service URL: http://localhost:8002
2024-01-01 10:00:00 | INFO     | MinIO Endpoint: localhost:9000
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 4. Verify Health

```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "services": {
    "orchestrator": "healthy",
    "indexing": "healthy",
    "agent": "healthy"
  }
}
```

### 5. Test Upload

```bash
# Upload a test file
curl -X POST http://localhost:8000/api/v1/upload \
  -F "file=@test.pdf" \
  -F 'config={"collection_name":"test","chunking_strategy":"recursive"}'
```

Expected response:
```json
{
  "status": "success",
  "message": "Document indexed successfully: 42 nodes",
  "collection_name": "test",
  "file_path": "raw-documents/2024-01-01/test.pdf",
  "node_count": 42
}
```

### 6. Test Chat

```bash
# Stream chat response
curl -N -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "测试消息",
    "config": {"collection_name": "test"},
    "thread_id": "test123"
  }'
```

Expected output (SSE stream):
```
data: {"content": "根据"}
data: {"content": "您的"}
data: {"content": "问题"}
...
```

## Docker Deployment

For production deployment with Docker Compose:

```bash
# From project root
docker compose up orchestrator

# Or start full stack
docker compose up
```

## Troubleshooting

### Port Already in Use

```bash
# Check what's using port 8000
netstat -ano | findstr :8000  # Windows
lsof -i :8000                 # Linux/Mac

# Change port in .env
PORT=8080
```

### Cannot Connect to Services

```bash
# Verify Indexing Service
curl http://localhost:8001/health

# Verify Agent Service
curl http://localhost:8002/health

# Verify MinIO
curl http://localhost:9000/minio/health/live
```

### MinIO Bucket Errors

```bash
# Check MinIO console
# Open http://localhost:9001 in browser
# Login with minioadmin/minioadmin
# Verify buckets: raw-documents, extracted-images
```

## Next Steps

- Read full [README.md](README.md) for API documentation
- Check [Refactoring Plan](../../docs/refactoring-plan.md) for architecture
- Explore API docs: http://localhost:8000/docs
