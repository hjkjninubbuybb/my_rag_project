"""API routes for Orchestrator Service."""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from sse_starlette.sse import EventSourceResponse
from typing import List
import json
import uuid

from app.schemas import (
    ChatRequest,
    IngestAndChatRequest,
    IngestAndChatResponse,
    UploadResponse,
    CollectionInfo,
    HealthResponse,
)
from app.services.indexing_client import IndexingClient
from app.services.agent_client import AgentClient
from app.services.minio_client import MinIOClient
from app.config import settings
from app.utils.logger import logger

router = APIRouter()

# Lazy-initialized clients (to avoid connection errors at import time)
_indexing_client = None
_agent_client = None
_minio_client = None


def get_indexing_client() -> IndexingClient:
    """Get or create IndexingClient."""
    global _indexing_client
    if _indexing_client is None:
        _indexing_client = IndexingClient(settings.indexing_url, settings.indexing_timeout)
    return _indexing_client


def get_agent_client() -> AgentClient:
    """Get or create AgentClient."""
    global _agent_client
    if _agent_client is None:
        _agent_client = AgentClient(settings.agent_url, settings.agent_timeout)
    return _agent_client


def get_minio_client() -> MinIOClient:
    """Get or create MinIOClient."""
    global _minio_client
    if _minio_client is None:
        _minio_client = MinIOClient(
            settings.minio_endpoint,
            settings.minio_access_key,
            settings.minio_secret_key,
            settings.minio_secure,
        )
    return _minio_client


@router.post("/api/v1/upload", response_model=UploadResponse)
async def upload_and_ingest(
    file: UploadFile = File(...),
    config: str = Form(...),
):
    """Upload file and trigger ingestion.

    Args:
        file: File to upload
        config: JSON string with ingestion configuration

    Returns:
        Upload and ingestion result
    """
    try:
        # Parse config
        config_dict = json.loads(config)
        logger.info(f"Uploading file: {file.filename}")

        # 1. Upload to MinIO
        file_data = await file.read()
        minio_path = get_minio_client().upload_file(file.filename, file_data)

        # 2. Call Indexing Service
        result = get_indexing_client().ingest(minio_path, config_dict)

        # 3. Return result
        return UploadResponse(
            status="success",
            message=f"Document indexed successfully: {result.get('node_count', 0)} nodes",
            collection_name=result.get("collection_name", ""),
            file_path=minio_path,
            node_count=result.get("node_count", 0),
        )

    except json.JSONDecodeError as e:
        logger.error(f"Invalid config JSON: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid config JSON: {e}")
    except Exception as e:
        logger.error(f"Upload and ingest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/chat")
async def chat(request: ChatRequest):
    """Stream chat response from Agent Service.

    Args:
        request: Chat request with message, config, thread_id

    Returns:
        SSE stream of chat response
    """
    try:
        logger.info(f"Chat request: thread_id={request.thread_id}")

        # Proxy Agent Service SSE stream
        async def event_generator():
            try:
                async for data in get_agent_client().chat_stream(
                    request.message, request.config, request.thread_id
                ):
                    yield {"data": data}
            except Exception as e:
                logger.error(f"Chat stream error: {e}")
                yield {"event": "error", "data": json.dumps({"error": str(e)})}

        return EventSourceResponse(event_generator())

    except Exception as e:
        logger.error(f"Chat failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/ingest-and-chat", response_model=IngestAndChatResponse)
async def ingest_and_chat(
    file: UploadFile = File(...),
    config: str = Form(...),
    message: str = Form(...),
    thread_id: str = Form(None),
):
    """End-to-end flow: upload, ingest, and chat.

    Args:
        file: File to upload
        config: JSON string with configuration
        message: User message for chat
        thread_id: Optional thread ID (generated if not provided)

    Returns:
        Combined result with ingestion stats and chat response
    """
    try:
        # Parse config
        config_dict = json.loads(config)
        logger.info(f"Ingest-and-chat: {file.filename}")

        # 1. Upload to MinIO
        file_data = await file.read()
        minio_path = get_minio_client().upload_file(file.filename, file_data)

        # 2. Call Indexing Service
        ingest_result = get_indexing_client().ingest(minio_path, config_dict)

        # 3. Generate thread_id if not provided
        if not thread_id:
            thread_id = str(uuid.uuid4())

        # 4. Call Agent Service (non-streaming for simplicity)
        # Collect full response from stream
        chat_response_parts = []
        async for data in get_agent_client().chat_stream(message, config_dict, thread_id):
            try:
                event_data = json.loads(data)
                if "content" in event_data:
                    chat_response_parts.append(event_data["content"])
            except json.JSONDecodeError:
                continue

        chat_response = "".join(chat_response_parts)

        # 5. Return combined result
        return IngestAndChatResponse(
            status="success",
            message="Document ingested and chat completed",
            file_path=minio_path,
            collection_name=ingest_result.get("collection_name", ""),
            node_count=ingest_result.get("node_count", 0),
            chat_response=chat_response,
        )

    except json.JSONDecodeError as e:
        logger.error(f"Invalid config JSON: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid config JSON: {e}")
    except Exception as e:
        logger.error(f"Ingest-and-chat failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/collections", response_model=List[CollectionInfo])
async def list_collections():
    """List all collections from Indexing Service.

    Returns:
        List of collection info
    """
    try:
        collections = get_indexing_client().list_collections()
        return [
            CollectionInfo(name=c["name"], point_count=c.get("point_count", 0))
            for c in collections
        ]
    except Exception as e:
        logger.error(f"List collections failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check for Orchestrator and downstream services.

    Returns:
        Health status of all services
    """
    services = {
        "orchestrator": "healthy",
        "indexing": "healthy" if get_indexing_client().health_check() else "unhealthy",
        "agent": "healthy" if get_agent_client().health_check() else "unhealthy",
    }

    # Overall status is healthy only if all services are healthy
    overall_status = "healthy" if all(s == "healthy" for s in services.values()) else "degraded"

    return HealthResponse(status=overall_status, services=services)
