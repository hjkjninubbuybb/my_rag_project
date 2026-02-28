# Agent Service Implementation Summary

## Overview

Implemented Agent Service (Phase 3) as a pure LLM/VLM service with LangGraph workflow. No direct database access - all retrieval goes through Indexing Service API.

## What Was Created

### Core Files

1. **pyproject.toml** - Poetry dependencies (numpy<2.0, langgraph, langchain, dashscope)
2. **app/main.py** - FastAPI application entry point
3. **app/config.py** - Service configuration (INDEXING_URL, DASHSCOPE_API_KEY)
4. **app/schemas.py** - Pydantic models for API requests/responses

### Agent Workflow (LangGraph)

5. **app/agent/workflow.py** - Main graph + subgraph (modified to use config dict)
6. **app/agent/nodes.py** - 5 nodes (summarize, rewrite, agent, extract, aggregate)
7. **app/agent/tools.py** - Modified to call Indexing Service API via httpx
8. **app/agent/state.py** - State definitions (copied from inference)
9. **app/agent/prompts.py** - System prompts (copied from inference)

### API Routes

10. **app/api/routes.py** - 4 endpoints:
    - POST /api/v1/chat (SSE streaming)
    - POST /api/v1/chat/reset
    - POST /api/v1/vlm/analyze (for Indexing Service)
    - POST /api/v1/vlm/summarize (batch)
    - GET /api/v1/health

### Services

11. **app/services/vlm.py** - VLM analysis service (DashScope Qwen-VL)

### Components

12. **app/components/providers/dashscope_llm.py** - Simplified LLM provider

### Utilities

13. **app/utils/logger.py** - Loguru logger

### Docker & Docs

14. **Dockerfile** - Multi-stage build with Poetry
15. **.env.example** - Environment variables template
16. **.gitignore** - Python/Poetry ignore patterns
17. **README.md** - Service documentation
18. **QUICKSTART.md** - Quick start guide
19. **test_service.sh** - Test script

## Key Design Decisions

### 1. No Shared Library Dependency

- **Before**: Used `rag_shared` for ComponentRegistry, ExperimentConfig, types
- **After**: Uses plain config dict, direct imports, no shared library
- **Reason**: Microservice independence, avoid circular dependencies

### 2. HTTP-Based Retrieval

- **Before**: Direct Qdrant/MySQL access via RetrievalService
- **After**: Calls Indexing Service `/api/v1/retrieve` API via httpx
- **Reason**: Service boundary enforcement, no database coupling

### 3. Simplified VLM Integration

- **Before**: ComponentRegistry.get_vlm_provider()
- **After**: Direct VLMService instantiation
- **Reason**: Simpler, no registry overhead

### 4. Config Dict Instead of ExperimentConfig

- **Before**: ExperimentConfig dataclass with validation
- **After**: Plain dict with .get() access
- **Reason**: No shared library, simpler for microservice

## API Changes

### Chat Endpoint

**Request**:
```json
{
  "message": "如何提交论文？",
  "config": {
    "collection_name": "manual_test",
    "llm_model": "qwen-plus",
    "retrieval_top_k": 5
  },
  "thread_id": "optional_thread_id"
}
```

**Response**: SSE events (token, rewrite, chunks, done, error)

### VLM Analyze Endpoint (NEW)

**Request**:
```json
{
  "image_base64": "...",
  "image_type": "screenshot",
  "surrounding_text": "上下文文本",
  "prompt": "可选自定义prompt"
}
```

**Response**:
```json
{
  "summary": "图像摘要文本",
  "confidence": 1.0
}
```

## Dependencies

### Key Packages

- **numpy<2.0** - LangChain compatibility
- **langgraph>=0.2** - Agent workflow
- **langchain>=0.2** - LLM abstractions
- **langchain-community>=0.2** - ChatTongyi (DashScope)
- **dashscope^1.25** - Qwen LLM/VLM
- **fastapi^0.115** - Web framework
- **sse-starlette^2.0** - SSE streaming
- **httpx^0.27** - HTTP client for Indexing Service
- **loguru^0.7** - Logging

## Testing Checklist

- [ ] Service starts successfully: `poetry run python -m app.main`
- [ ] Health check works: `curl http://localhost:8002/api/v1/health`
- [ ] VLM analyze works (with valid API key)
- [ ] Chat endpoint works (requires Indexing Service)
- [ ] SSE streaming works
- [ ] Docker build succeeds: `docker build -t rag-agent .`
- [ ] Docker run succeeds

## Integration Points

### Upstream (Calls Agent Service)

- **Orchestrator Service** (Phase 4) - Will call /api/v1/chat for user queries

### Downstream (Agent Service Calls)

- **Indexing Service** (Phase 2) - Calls /api/v1/retrieve for knowledge retrieval

### Bidirectional

- **Indexing Service** ↔ **Agent Service**:
  - Ingestion flow: Indexing → Agent `/api/v1/vlm/analyze` (VLM summaries)
  - Query flow: Agent → Indexing `/api/v1/retrieve` (knowledge retrieval)

## Next Steps

1. **Test Agent Service standalone** (with mock Indexing Service)
2. **Implement Indexing Service** (Phase 2) with /api/v1/retrieve endpoint
3. **Test end-to-end flow**: Orchestrator → Agent → Indexing → Qdrant/MySQL
4. **Performance tuning**: Graph caching, connection pooling, timeout settings

## Known Limitations

1. **MemorySaver**: In-memory checkpointer, no persistence (reset = new thread_id)
2. **No retry logic**: HTTP calls to Indexing Service don't retry on failure
3. **No circuit breaker**: No fallback if Indexing Service is down
4. **Simplified VLM**: Only uses first image in multimodal context
5. **No streaming to VLM**: VLM calls are blocking (not async)

## Files Modified from Inference Service

- **nodes.py**: Removed ComponentRegistry, simplified VLM integration
- **tools.py**: Replaced RetrievalService with httpx API call
- **workflow.py**: Removed ExperimentConfig, uses config dict
- **state.py**: No changes (copied as-is)
- **prompts.py**: No changes (copied as-is)

## Total Files Created

- 19 new files
- ~1500 lines of code
- 0 dependencies on shared library
- 100% microservice architecture compliant
