"""API routes for Indexing Service."""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.config.experiment import ExperimentConfig
from app.services.ingestion import IngestionService
from app.services.retrieval import RetrievalService
from app.services.multimodal_retrieval import MultimodalRetrievalService
from app.storage.vectordb import VectorStoreManager
from app.storage.mysql_client import MySQLClient
from app.storage.minio_client import MinIOClient
from app.utils.logger import logger

router = APIRouter()

# Initialize clients (will be set in lifespan)
vector_store: Optional[VectorStoreManager] = None
mysql_client: Optional[MySQLClient] = None
minio_client: Optional[MinIOClient] = None


# ──────────────────── Request/Response Models ────────────────────


class IndexRequest(BaseModel):
    """Request model for indexing documents."""

    minio_path: str = Field(..., description="MinIO object path (e.g., 'raw-documents/manual.pdf')")
    config: Dict[str, Any] = Field(..., description="Experiment configuration")


class IndexResponse(BaseModel):
    """Response model for indexing."""

    status: str
    message: str
    collection_name: str
    vectorized_count: int
    parent_count: Optional[int] = None
    child_count: Optional[int] = None
    is_hierarchical: bool = False


class RetrieveRequest(BaseModel):
    """Request model for retrieval."""

    query: str = Field(..., description="Search query")
    config: Dict[str, Any] = Field(..., description="Experiment configuration")
    top_k: int = Field(5, description="Number of results to return")


class RetrieveResponse(BaseModel):
    """Response model for retrieval."""

    nodes: List[Dict[str, Any]]


class CollectionInfo(BaseModel):
    """Collection information."""

    name: str
    point_count: int
    created_at: Optional[str] = None


class FileInfo(BaseModel):
    """File information."""

    file_name: str


class DocumentDeleteResponse(BaseModel):
    """Response for document deletion."""

    status: str
    message: str
    deleted_count: int


# ──────────────────── API Endpoints ────────────────────


@router.post("/api/v1/index", response_model=IndexResponse)
async def index_document(request: IndexRequest):
    """Index a document from MinIO.

    Flow:
    1. Download file from MinIO
    2. Parse document (PDF/DOCX)
    3. Clean text (PolicyCleaner/ManualCleaner)
    4. Chunk document
    5. [TODO Phase 3] Call Agent VLM API for image summaries
    6. Embed chunks (text + sparse + [image])
    7. Store in Qdrant + MySQL
    """
    try:
        # Parse config
        config = ExperimentConfig(**request.config)

        # Download file from MinIO
        bucket_name, object_name = request.minio_path.split("/", 1)
        file_data = minio_client.download_file(bucket_name, object_name)
        file_name = object_name.split("/")[-1]

        # Initialize ingestion service
        ingestion_service = IngestionService(
            vector_store=vector_store,
            mysql_client=mysql_client,
            config=config,
        )

        # Ingest document
        result = await ingestion_service.ingest_from_bytes(
            file_data=file_data,
            file_name=file_name,
            config=config,
        )

        return IndexResponse(
            status="success",
            message=result.get("message", "Document indexed successfully"),
            collection_name=result["collection_name"],
            vectorized_count=result.get("vectorized_count", 0),
            parent_count=result.get("parent_count"),
            child_count=result.get("child_count"),
            is_hierarchical=result.get("is_hierarchical", False),
        )

    except Exception as e:
        logger.error(f"Failed to index document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Indexing failed: {str(e)}",
        )


@router.post("/api/v1/retrieve", response_model=RetrieveResponse)
async def retrieve(request: RetrieveRequest):
    """Retrieve relevant documents.

    Supports:
    - Dense retrieval (text embeddings)
    - Sparse retrieval (jieba BM25)
    - Hybrid retrieval (dense + sparse)
    - Reranking
    - Role-based filtering
    """
    try:
        # Parse config
        config = ExperimentConfig(**request.config)

        # Choose retrieval service based on multimodal flag
        if config.enable_multimodal:
            retrieval_service = MultimodalRetrievalService(
                vector_store=vector_store,
                mysql_client=mysql_client,
                config=config,
            )
        else:
            retrieval_service = RetrievalService(
                vector_store=vector_store,
                config=config,
            )

        # Retrieve nodes
        nodes = await retrieval_service.retrieve(
            query=request.query,
            top_k=request.top_k,
        )

        # Format response
        formatted_nodes = [
            {
                "text": node.text,
                "score": node.score,
                "source_file": node.metadata.get("file_name", "unknown"),
                "page": node.metadata.get("page"),
                "node_type": node.metadata.get("node_type", "text"),
                "metadata": node.metadata,
            }
            for node in nodes
        ]

        return RetrieveResponse(nodes=formatted_nodes)

    except Exception as e:
        logger.error(f"Failed to retrieve: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retrieval failed: {str(e)}",
        )


@router.get("/api/v1/collections", response_model=List[CollectionInfo])
async def list_collections():
    """List all Qdrant collections with metadata."""
    try:
        # Get collections from Qdrant
        qdrant_collections = vector_store.list_collections()

        # Get metadata from MySQL
        mysql_collections = mysql_client.list_collections()
        mysql_map = {c["name"]: c for c in mysql_collections}

        # Merge data
        result = []
        for coll in qdrant_collections:
            mysql_data = mysql_map.get(coll["name"], {})
            result.append(
                CollectionInfo(
                    name=coll["name"],
                    point_count=coll.get("point_count", 0),
                    created_at=mysql_data.get("created_at"),
                )
            )

        return result

    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list collections: {str(e)}",
        )


@router.get("/api/v1/collections/{collection_name}/files", response_model=List[FileInfo])
async def list_files(collection_name: str):
    """List all files in a collection."""
    try:
        file_names = mysql_client.list_documents(collection_name)
        return [FileInfo(file_name=name) for name in file_names]

    except Exception as e:
        logger.error(f"Failed to list files: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list files: {str(e)}",
        )


@router.delete("/api/v1/collections/{collection_name}")
async def delete_collection(collection_name: str):
    """Delete entire collection from Qdrant and MySQL."""
    try:
        # Delete from Qdrant
        vector_store.delete_collection(collection_name)

        # Delete from MySQL
        mysql_client.delete_collection(collection_name)

        # Delete all documents metadata
        documents = mysql_client.list_documents(collection_name)
        for doc in documents:
            mysql_client.delete_document(collection_name, doc)

        # Delete all parent nodes
        # Note: This is a bulk operation, might need optimization

        return {
            "status": "success",
            "message": f"Collection {collection_name} deleted",
        }

    except Exception as e:
        logger.error(f"Failed to delete collection: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete collection: {str(e)}",
        )


@router.delete("/api/v1/documents/{collection_name}/{file_name}", response_model=DocumentDeleteResponse)
async def delete_document(collection_name: str, file_name: str):
    """Delete a specific document from collection."""
    try:
        # Delete from Qdrant (filter by file_name metadata)
        deleted_count = vector_store.delete_by_metadata(
            collection_name=collection_name,
            metadata_filter={"file_name": file_name},
        )

        # Delete parent nodes from MySQL
        mysql_client.delete_parent_nodes_by_collection_and_file(
            collection_name=collection_name,
            file_name=file_name,
        )

        # Delete document metadata
        mysql_client.delete_document(collection_name, file_name)

        return DocumentDeleteResponse(
            status="success",
            message=f"Document {file_name} deleted from {collection_name}",
            deleted_count=deleted_count,
        )

    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}",
        )


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "indexing",
        "version": "1.0.0",
    }
