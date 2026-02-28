# Orchestrator Service

User entry point for the RAG system. Orchestrates file uploads, ingestion, and chat workflows by coordinating Indexing and Agent services.

## Architecture

**Port**: 8000

**Responsibilities**:
- File upload to MinIO
- Orchestrate ingestion flow (Indexing Service)
- Orchestrate chat flow (Agent Service)
- No business logic (pure orchestration)

**Dependencies**:
- Indexing Service (port 8001)
- Agent Service (port 8002)
- MinIO (port 9000)

## API Endpoints

### POST /api/v1/upload
Upload file and trigger ingestion.

**Request**:
```bash
curl -X POST http://localhost:8000/api/v1/upload \
  -F "file=@document.pdf" \
  -F 'config={"collection_name":"test","chunking_strategy":"recursive"}'
```

**Response**:
```json
{
  "status": "success",
  "message": "Document indexed successfully: 42 nodes",
  "collection_name": "test",
  "file_path": "raw-documents/2024-01-01/document.pdf",
  "node_count": 42
}
```

### POST /api/v1/chat
Stream chat response (SSE).

**Request**:
```bash
curl -N -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "如何提交毕业论文？",
    "config": {"collection_name": "manual_test"},
    "thread_id": "abc123"
  }'
```

**Response**: SSE stream
```
data: {"content": "根据"}
data: {"content": "系统"}
data: {"content": "操作"}
...
```

### POST /api/v1/ingest-and-chat
End-to-end flow: upload, ingest, and chat.

**Request**:
```bash
curl -X POST http://localhost:8000/api/v1/ingest-and-chat \
  -F "file=@document.pdf" \
  -F 'config={"collection_name":"test"}' \
  -F "message=总结这个文档" \
  -F "thread_id=xyz789"
```

**Response**:
```json
{
  "status": "success",
  "message": "Document ingested and chat completed",
  "file_path": "raw-documents/2024-01-01/document.pdf",
  "collection_name": "test",
  "node_count": 42,
  "chat_response": "这个文档主要讲述了..."
}
```

### GET /api/v1/collections
List all collections.

**Request**:
```bash
curl http://localhost:8000/api/v1/collections
```

**Response**:
```json
[
  {"name": "manual_test", "point_count": 150},
  {"name": "policy_docs", "point_count": 89}
]
```

### GET /health
Health check for all services.

**Request**:
```bash
curl http://localhost:8000/health
```

**Response**:
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

## Quick Start

### Local Development

1. **Install dependencies**:
```bash
cd services/orchestrator
poetry install
```

2. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with local URLs (localhost instead of service names)
```

3. **Start service**:
```bash
poetry run python -m app.main
```

4. **Test**:
```bash
# Health check
curl http://localhost:8000/health

# Upload file
curl -X POST http://localhost:8000/api/v1/upload \
  -F "file=@test.pdf" \
  -F 'config={"collection_name":"test"}'
```

### Docker Deployment

See root `docker-compose.yml` for full stack deployment.

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `INDEXING_URL` | `http://indexing:8001` | Indexing Service URL |
| `AGENT_URL` | `http://agent:8002` | Agent Service URL |
| `MINIO_ENDPOINT` | `minio:9000` | MinIO endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `MINIO_SECURE` | `false` | Use HTTPS for MinIO |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8000` | Server port |
| `INDEXING_TIMEOUT` | `300.0` | Indexing request timeout (seconds) |
| `AGENT_TIMEOUT` | `300.0` | Agent request timeout (seconds) |

## Architecture Notes

### Service Boundaries
- **NO parsing**: File parsing is done by Indexing Service
- **NO vectorization**: Embedding is done by Indexing Service
- **NO LLM reasoning**: Chat is handled by Agent Service
- **Pure orchestration**: Only coordinates workflows

### MinIO Buckets
- `raw-documents`: Uploaded files (organized by date: YYYY-MM-DD/filename)
- `extracted-images`: Images extracted from PDFs (managed by Indexing Service)

### Error Handling
- Catches downstream service errors
- Returns friendly HTTP error responses
- Logs all errors for debugging

### Timeouts
- Default: 300 seconds (5 minutes)
- Configurable per service (indexing, agent)
- Health checks: 5 seconds

## Development

### Project Structure
```
services/orchestrator/
├── app/
│   ├── main.py              # FastAPI app
│   ├── config.py            # Settings
│   ├── schemas.py           # Pydantic models
│   ├── api/
│   │   └── routes.py        # API endpoints
│   ├── services/
│   │   ├── indexing_client.py   # Indexing Service client
│   │   ├── agent_client.py      # Agent Service client
│   │   └── minio_client.py      # MinIO client
│   └── utils/
│       └── logger.py        # Logging
├── pyproject.toml           # Poetry dependencies
├── Dockerfile               # Docker image
└── .env.example             # Environment template
```

### Adding New Endpoints

1. Add schema to `app/schemas.py`
2. Add route to `app/api/routes.py`
3. Call downstream services via clients
4. Return orchestrated result

### Testing

```bash
# Install dev dependencies
poetry install

# Run tests (when implemented)
poetry run pytest
```

## Troubleshooting

### Service Connection Errors

**Symptom**: `Cannot connect to Indexing/Agent Service`

**Solution**:
- Check service URLs in `.env`
- Docker: Use service names (`indexing`, `agent`)
- Local: Use `localhost`
- Verify services are running: `curl http://localhost:8001/health`

### MinIO Connection Errors

**Symptom**: `MinIO bucket creation failed`

**Solution**:
- Check MinIO is running: `curl http://localhost:9000/minio/health/live`
- Verify credentials in `.env`
- Check bucket permissions

### Timeout Errors

**Symptom**: `Request timeout after 300s`

**Solution**:
- Increase timeout in `.env`: `INDEXING_TIMEOUT=600.0`
- Check downstream service logs
- Verify file size is reasonable

## Related Documentation

- [Refactoring Plan](../../docs/refactoring-plan.md) - Full architecture
- [CLAUDE.md](../../CLAUDE.md) - System overview
- Indexing Service: `services/indexing/README.md`
- Agent Service: `services/agent/README.md`
