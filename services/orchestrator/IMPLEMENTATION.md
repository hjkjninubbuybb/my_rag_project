# Orchestrator Service - Implementation Summary

## Overview

Successfully implemented the Orchestrator Service (Phase 4 of refactoring plan) as the user entry point for the RAG system.

## Implementation Date

2024-02-28

## Directory Structure

```
services/orchestrator/
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app with lifespan
│   ├── config.py                    # ServiceSettings (Pydantic)
│   ├── schemas.py                   # Request/Response models
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py                # 5 API endpoints
│   ├── services/
│   │   ├── __init__.py
│   │   ├── indexing_client.py       # HTTP client for Indexing Service
│   │   ├── agent_client.py          # HTTP client for Agent Service (SSE)
│   │   └── minio_client.py          # MinIO object storage client
│   └── utils/
│       ├── __init__.py
│       └── logger.py                # Loguru logger
├── pyproject.toml                   # Poetry dependencies
├── poetry.lock                      # Locked dependencies
├── Dockerfile                       # Production Docker image
├── .env.example                     # Environment template
├── README.md                        # Full documentation
├── QUICKSTART.md                    # Quick start guide
└── test_structure.py                # Structure verification test
```

## API Endpoints (5 total)

### 1. POST /api/v1/upload
Upload file to MinIO and trigger ingestion via Indexing Service.

**Flow**: File → MinIO → Indexing Service → Response

### 2. POST /api/v1/chat
Stream chat response from Agent Service (SSE).

**Flow**: Request → Agent Service → SSE Stream → Client

### 3. POST /api/v1/ingest-and-chat
End-to-end flow: upload, ingest, and chat in one request.

**Flow**: File → MinIO → Indexing Service → Agent Service → Response

### 4. GET /api/v1/collections
List all collections from Indexing Service.

**Flow**: Request → Indexing Service → Collection List

### 5. GET /health
Health check for Orchestrator and all downstream services.

**Flow**: Check self + Indexing + Agent → Health Status

## Key Design Decisions

### 1. Lazy Client Initialization
Clients are initialized on first use (not at module import) to avoid connection errors during testing and imports.

```python
def get_minio_client() -> MinIOClient:
    global _minio_client
    if _minio_client is None:
        _minio_client = MinIOClient(...)
    return _minio_client
```

### 2. Pure Orchestration
- NO parsing logic
- NO vectorization logic
- NO LLM reasoning
- ONLY coordinates workflows between services

### 3. MinIO File Storage
- Bucket: `raw-documents`
- Path format: `YYYY-MM-DD/filename`
- Auto-creates buckets on first use

### 4. SSE Streaming Proxy
Proxies Agent Service SSE stream to client without buffering.

### 5. Error Handling
- Catches downstream service errors
- Returns friendly HTTP error responses
- Logs all errors with context

## Dependencies

### Core
- fastapi ^0.109.0
- uvicorn ^0.27.0
- httpx ^0.26.0 (HTTP client)
- sse-starlette ^2.0.0 (SSE streaming)
- minio ^7.2.0 (object storage)

### Configuration
- pydantic ^2.5.0
- pydantic-settings ^2.1.0

### Utilities
- python-multipart ^0.0.6 (file uploads)
- loguru ^0.7.2 (logging)

### Dev
- pytest ^7.4.0
- pytest-asyncio ^0.21.0

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| INDEXING_URL | http://indexing:8001 | Indexing Service URL |
| AGENT_URL | http://agent:8002 | Agent Service URL |
| MINIO_ENDPOINT | minio:9000 | MinIO endpoint |
| MINIO_ACCESS_KEY | minioadmin | MinIO access key |
| MINIO_SECRET_KEY | minioadmin | MinIO secret key |
| MINIO_SECURE | false | Use HTTPS for MinIO |
| HOST | 0.0.0.0 | Server host |
| PORT | 8000 | Server port |
| INDEXING_TIMEOUT | 300.0 | Indexing request timeout (seconds) |
| AGENT_TIMEOUT | 300.0 | Agent request timeout (seconds) |

## Testing

### Structure Verification
```bash
poetry run python test_structure.py
```

**Results**: All imports successful, all routes verified.

### Manual Testing
```bash
# Start service
poetry run python -m app.main

# Health check
curl http://localhost:8000/health

# Upload file
curl -X POST http://localhost:8000/api/v1/upload \
  -F "file=@test.pdf" \
  -F 'config={"collection_name":"test"}'

# Chat
curl -N -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"测试","config":{},"thread_id":"test123"}'
```

## Docker Deployment

### Dockerfile Features
- Python 3.10 slim base image
- Poetry for dependency management
- Health check endpoint
- Non-root user (implicit)

### Build & Run
```bash
# Build
docker build -t orchestrator:latest .

# Run
docker run -p 8000:8000 \
  -e INDEXING_URL=http://indexing:8001 \
  -e AGENT_URL=http://agent:8002 \
  -e MINIO_ENDPOINT=minio:9000 \
  orchestrator:latest
```

## Service Boundaries (CRITICAL)

### What Orchestrator DOES
- Accept file uploads
- Store files in MinIO
- Call Indexing Service for ingestion
- Call Agent Service for chat
- Proxy SSE streams
- Health checks

### What Orchestrator DOES NOT DO
- Parse documents (Indexing Service)
- Chunk text (Indexing Service)
- Generate embeddings (Indexing Service)
- Store vectors (Indexing Service)
- LLM reasoning (Agent Service)
- VLM analysis (Agent Service)

## Integration Points

### With Indexing Service
- POST /api/v1/ingest - Trigger ingestion
- POST /api/v1/retrieve - Search documents (future)
- GET /api/v1/collections - List collections
- GET /health - Health check

### With Agent Service
- POST /api/v1/chat - Stream chat (SSE)
- POST /api/v1/vlm/analyze - VLM analysis (future)
- GET /health - Health check

### With MinIO
- Bucket: raw-documents (write)
- Bucket: extracted-images (read, future)

## Next Steps

1. **Integration Testing**: Test with real Indexing and Agent services
2. **Docker Compose**: Add to root docker-compose.yml
3. **Monitoring**: Add metrics and tracing
4. **Rate Limiting**: Add rate limiting for public endpoints
5. **Authentication**: Add API key authentication (future)

## Known Limitations

1. **No Authentication**: Currently no auth (add in future)
2. **No Rate Limiting**: No rate limiting (add in future)
3. **No Caching**: No response caching (add if needed)
4. **No Retry Logic**: No automatic retries for downstream failures (add if needed)
5. **Memory Buffering**: ingest-and-chat buffers full chat response in memory (acceptable for now)

## Verification Checklist

- [x] Directory structure created
- [x] All 5 API endpoints implemented
- [x] 3 service clients implemented (Indexing, Agent, MinIO)
- [x] Configuration management (Pydantic Settings)
- [x] Logging (Loguru)
- [x] Error handling
- [x] Dockerfile
- [x] .env.example
- [x] README.md
- [x] QUICKSTART.md
- [x] Structure verification test
- [x] Poetry dependencies locked
- [x] All imports successful
- [x] All routes verified

## Files Created

Total: 17 files

### Core Application (12 files)
1. app/__init__.py
2. app/main.py
3. app/config.py
4. app/schemas.py
5. app/api/__init__.py
6. app/api/routes.py
7. app/services/__init__.py
8. app/services/indexing_client.py
9. app/services/agent_client.py
10. app/services/minio_client.py
11. app/utils/__init__.py
12. app/utils/logger.py

### Configuration & Documentation (5 files)
13. pyproject.toml
14. Dockerfile
15. .env.example
16. README.md
17. QUICKSTART.md

### Testing (1 file)
18. test_structure.py

### Generated (1 file)
19. poetry.lock

## Implementation Notes

### Lazy Initialization Pattern
Used to avoid connection errors at import time. Clients are created on first use.

### SSE Streaming
Uses `sse-starlette.EventSourceResponse` to proxy Agent Service SSE stream without buffering.

### MinIO Auto-Setup
Automatically creates required buckets (`raw-documents`, `extracted-images`) on first use.

### Health Check Strategy
- Self: Always healthy (if responding)
- Downstream: Check with 5s timeout
- Overall: Degraded if any downstream unhealthy

### Error Response Format
```json
{
  "detail": "Error message"
}
```

## Performance Considerations

### Timeouts
- Default: 300s (5 minutes) for ingestion and chat
- Health checks: 5s
- Configurable via environment variables

### Concurrency
- FastAPI async endpoints for I/O-bound operations
- httpx async client for Agent Service streaming
- httpx sync client for Indexing Service (simpler)

### Memory
- File uploads: Buffered in memory (acceptable for PDFs <100MB)
- SSE streaming: No buffering (streamed directly)
- ingest-and-chat: Buffers chat response (acceptable for typical responses)

## Security Considerations

### Current State
- No authentication
- No rate limiting
- No input validation beyond Pydantic schemas
- No CORS configuration

### Future Enhancements
- Add API key authentication
- Add rate limiting (per IP, per user)
- Add input size limits
- Add CORS configuration for web clients
- Add request signing for service-to-service calls

## Maintenance

### Logging
All operations logged with context (file names, collection names, errors).

### Monitoring
Health endpoint provides service status. Add metrics in future:
- Request count
- Response time
- Error rate
- Downstream service availability

### Debugging
- Structured logging with loguru
- Request/response logging
- Error stack traces

## Related Documentation

- [Refactoring Plan](../../docs/refactoring-plan.md) - Full architecture
- [CLAUDE.md](../../CLAUDE.md) - System overview
- [README.md](README.md) - API documentation
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
