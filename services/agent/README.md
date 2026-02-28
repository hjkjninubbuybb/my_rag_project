# Agent Service

Pure LLM/VLM service with LangGraph workflow. No direct database access.

## Features

- **LangGraph Agent Workflow**: ReAct loop with parallel question routing
- **SSE Streaming**: Real-time token streaming for chat responses
- **VLM Analysis**: Image analysis and summarization via DashScope Qwen-VL
- **No Database Access**: Calls Indexing Service API for retrieval

## Architecture

```
User → Agent Service → Indexing Service → Qdrant/MySQL
         ↓
    LangGraph Workflow
    (summarize → rewrite → route → process → aggregate)
```

## API Endpoints

### Chat

- `POST /api/v1/chat` - SSE streaming chat
- `POST /api/v1/chat/reset` - Reset conversation (use new thread_id)

### VLM

- `POST /api/v1/vlm/analyze` - Single image analysis (for Indexing Service)
- `POST /api/v1/vlm/summarize` - Batch image summarization

### Health

- `GET /api/v1/health` - Health check

## Setup

### Local Development

```bash
# Install dependencies
poetry install

# Copy environment file
cp .env.example .env

# Edit .env and set DASHSCOPE_API_KEY

# Run service
poetry run python -m app.main
```

### Docker

```bash
# Build image
docker build -t rag-agent:latest .

# Run container
docker run -d \
  -p 8002:8002 \
  -e DASHSCOPE_API_KEY=your_key \
  -e INDEXING_URL=http://indexing:8001 \
  --name rag-agent \
  rag-agent:latest
```

## Configuration

Environment variables:

- `DASHSCOPE_API_KEY` - DashScope API key (required)
- `INDEXING_URL` - Indexing Service URL (default: http://localhost:8001)
- `HOST` - Service host (default: 0.0.0.0)
- `PORT` - Service port (default: 8002)

## Dependencies

- **numpy<2.0** - LangChain compatibility
- **langgraph** - Agent workflow
- **langchain** - LLM abstractions
- **dashscope** - Qwen LLM/VLM
- **fastapi** - Web framework
- **sse-starlette** - SSE streaming
- **httpx** - HTTP client for Indexing Service

## Key Design Decisions

1. **No Database Access**: All retrieval goes through Indexing Service API
2. **Config Dict**: Uses plain dict instead of ExperimentConfig (no shared library)
3. **MemorySaver**: In-memory checkpointer (reset = new thread_id)
4. **Graph Caching**: LangGraph instances cached by (llm_model, collection_name)

## Testing

```bash
# Health check
curl http://localhost:8002/api/v1/health

# VLM analyze
curl -X POST http://localhost:8002/api/v1/vlm/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "image_base64": "...",
    "image_type": "screenshot",
    "surrounding_text": "上下文文本"
  }'

# Chat (requires Indexing Service running)
curl -N -X POST http://localhost:8002/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "如何提交论文？",
    "config": {
      "collection_name": "manual_test",
      "llm_model": "qwen-plus"
    }
  }'
```

## Troubleshooting

### "Indexing Service 检索失败"

- Check `INDEXING_URL` is correct
- Verify Indexing Service is running: `curl http://localhost:8001/api/v1/health`

### "VLM 调用失败"

- Check `DASHSCOPE_API_KEY` is valid
- Verify network access to DashScope API

### SSE Stream Interrupted

- Check `recursion_limit` in workflow (default: 25)
- Increase timeout if needed
- Check Indexing Service response time
