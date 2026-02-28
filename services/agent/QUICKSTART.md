# Agent Service - Quick Start Guide

## Prerequisites

- Python 3.11+
- Poetry
- DashScope API Key
- Indexing Service running (for retrieval)

## Installation

```bash
cd services/agent

# Install dependencies
poetry install

# Copy environment file
cp .env.example .env

# Edit .env and set your DASHSCOPE_API_KEY
nano .env
```

## Running the Service

### Local Development

```bash
# Run with Poetry
poetry run python -m app.main

# Or activate virtual environment first
poetry shell
python -m app.main
```

The service will start on http://localhost:8002

### Docker

```bash
# Build image
docker build -t rag-agent:latest .

# Run container
docker run -d \
  -p 8002:8002 \
  -e DASHSCOPE_API_KEY=your_key_here \
  -e INDEXING_URL=http://indexing:8001 \
  --name rag-agent \
  rag-agent:latest

# Check logs
docker logs -f rag-agent
```

## Testing

### 1. Health Check

```bash
curl http://localhost:8002/api/v1/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "agent",
  "indexing_url": "http://localhost:8001"
}
```

### 2. VLM Image Analysis

```bash
curl -X POST http://localhost:8002/api/v1/vlm/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "image_base64": "<your_base64_image>",
    "image_type": "screenshot",
    "surrounding_text": "这是系统登录页面"
  }'
```

### 3. Chat (SSE Streaming)

**Note**: Requires Indexing Service to be running!

```bash
curl -N -X POST http://localhost:8002/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "如何提交毕业论文？",
    "config": {
      "collection_name": "manual_test",
      "llm_model": "qwen-plus",
      "retrieval_top_k": 5
    }
  }'
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/chat` | POST | SSE streaming chat |
| `/api/v1/chat/reset` | POST | Reset conversation |
| `/api/v1/vlm/analyze` | POST | Single image analysis |
| `/api/v1/vlm/summarize` | POST | Batch image summarization |

## Configuration

Edit `.env` file:

```bash
# Required
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxx

# Optional
INDEXING_URL=http://localhost:8001
HOST=0.0.0.0
PORT=8002
```

## Troubleshooting

### Service won't start

1. Check Python version: `python --version` (should be 3.11+)
2. Check Poetry installation: `poetry --version`
3. Reinstall dependencies: `poetry install --no-cache`

### "Indexing Service 检索失败"

1. Verify Indexing Service is running:
   ```bash
   curl http://localhost:8001/api/v1/health
   ```
2. Check `INDEXING_URL` in `.env`
3. Check network connectivity

### "VLM 调用失败"

1. Verify `DASHSCOPE_API_KEY` is set correctly
2. Check API key validity
3. Check network access to DashScope API

### SSE stream interrupted

1. Check Indexing Service response time
2. Increase `recursion_limit` in workflow.py if needed
3. Check logs: `docker logs -f rag-agent`

## Development

### Project Structure

```
services/agent/
├── app/
│   ├── agent/          # LangGraph workflow
│   │   ├── workflow.py # Main graph
│   │   ├── nodes.py    # Graph nodes
│   │   ├── tools.py    # Agent tools
│   │   ├── state.py    # State definitions
│   │   └── prompts.py  # System prompts
│   ├── api/
│   │   └── routes.py   # FastAPI routes
│   ├── services/
│   │   └── vlm.py      # VLM service
│   ├── components/
│   │   └── providers/  # LLM providers
│   ├── utils/
│   │   └── logger.py   # Logging
│   ├── config.py       # Configuration
│   ├── main.py         # FastAPI app
│   └── schemas.py      # Pydantic models
├── pyproject.toml      # Dependencies
├── Dockerfile          # Docker build
└── README.md           # Documentation
```

### Adding New Features

1. **New LLM Provider**: Add to `app/components/providers/`
2. **New Agent Node**: Add to `app/agent/nodes.py`
3. **New API Endpoint**: Add to `app/api/routes.py`
4. **New Tool**: Add to `app/agent/tools.py`

## Next Steps

1. Start Indexing Service (Phase 2)
2. Test end-to-end chat flow
3. Integrate with Orchestrator Service (Phase 4)
