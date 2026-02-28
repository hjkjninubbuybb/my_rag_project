"""Pydantic schemas for Orchestrator Service."""
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    """Response for file upload."""
    status: str
    message: str
    collection_name: str
    file_path: str
    node_count: int


class ChatRequest(BaseModel):
    """Request for chat endpoint."""
    message: str
    config: Dict[str, Any] = Field(default_factory=dict)
    thread_id: str


class IngestAndChatRequest(BaseModel):
    """Request for ingest-and-chat endpoint."""
    config: Dict[str, Any] = Field(default_factory=dict)
    message: str
    thread_id: Optional[str] = None


class IngestAndChatResponse(BaseModel):
    """Response for ingest-and-chat endpoint."""
    status: str
    message: str
    file_path: str
    collection_name: str
    node_count: int
    chat_response: str


class CollectionInfo(BaseModel):
    """Collection information."""
    name: str
    point_count: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    services: Dict[str, str]
