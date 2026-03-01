"""API routes for Indexing Service."""

import json
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, UploadFile, Form, status
from pydantic import BaseModel, Field

from app.config import settings
from app.config.experiment import ExperimentConfig
from app.services.ingestion import IngestionService
from app.services.retrieval import RetrievalService
from app.services.multimodal_retrieval import MultimodalRetrievalService
from app.storage.vectordb import VectorStoreManager
from app.storage.mysql_client import MySQLClient
from app.utils.logger import logger

router = APIRouter()

# Initialize clients (will be set in lifespan)
vector_store: Optional[VectorStoreManager] = None
mysql_client: Optional[MySQLClient] = None


# ──────────────────── Request/Response Models ────────────────────


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


class ConvertToMarkdownResponse(BaseModel):
    """Response model for PDF to Markdown conversion."""

    status: str
    filename: str
    pages: int
    image_count: int
    images: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Extracted images [{name, format, data_base64}]",
    )
    markdown_content: str = Field(
        ..., description="Full generated Markdown content"
    )


class ExtractImageInfo(BaseModel):
    """Extracted image info (without raw bytes)."""

    bbox: Optional[List[float]] = None
    format: str
    width: int
    height: int
    hash: str
    image_type: str
    surrounding_text: str


class ExtractPageResult(BaseModel):
    """Extraction result for a single page."""

    page: int
    text: str
    images: List[ExtractImageInfo]
    role: str


class ExtractResponse(BaseModel):
    """Response model for document extraction."""

    status: str
    filename: str
    total_pages: int
    total_images: int
    pages: List[ExtractPageResult]


# ──────────────────── API Endpoints ────────────────────


@router.post("/api/v1/index", response_model=IndexResponse)
async def index_document(file: UploadFile, config: str = Form("{}")):
    """Index an uploaded document.

    Flow:
    1. Read uploaded file
    2. Parse document (PDF/DOCX)
    3. Clean text (PolicyCleaner/ManualCleaner)
    4. Chunk document
    5. [TODO Phase 3] Call Agent VLM API for image summaries
    6. Embed chunks (text + sparse + [image])
    7. Store in Qdrant + MySQL
    """
    try:
        # Parse config
        config_dict = json.loads(config)
        exp_config = ExperimentConfig(**config_dict)

        # Read uploaded file
        file_data = await file.read()
        file_name = file.filename

        # Initialize ingestion service
        ingestion_service = IngestionService(
            vector_store=vector_store,
            mysql_client=mysql_client,
            config=exp_config,
        )

        # Ingest document
        result = await ingestion_service.ingest_from_bytes(
            file_data=file_data,
            file_name=file_name,
            config=exp_config,
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


@router.post("/api/v1/convert-to-markdown", response_model=ConvertToMarkdownResponse)
async def convert_to_markdown(file: UploadFile):
    """Convert a PDF to Markdown with extracted images.

    Flow:
    1. Read uploaded PDF
    2. Extract images (MultimodalPDFParser)
    3. Parse per-page Markdown (MinerUParser)
    4. Inject image references by page number
    5. Return markdown content + images as base64
    """
    try:
        from app.services.pdf_to_markdown import PDFToMarkdownService

        # Read uploaded file
        file_data = await file.read()
        file_name = file.filename

        # Convert
        service = PDFToMarkdownService()
        result = service.convert(file_data, file_name)

        return ConvertToMarkdownResponse(
            status="success",
            filename=result.filename,
            pages=result.pages,
            image_count=result.image_count,
            images=result.images,
            markdown_content=result.markdown_content,
        )

    except Exception as e:
        logger.error(f"Failed to convert PDF to Markdown: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Conversion failed: {str(e)}",
        )


@router.post("/api/v1/extract", response_model=ExtractResponse)
async def extract_document(file: UploadFile):
    """Extract text and images from a PDF (parse only, no ingestion).

    Uses MultimodalPDFParser to extract per-page text and image metadata.
    Useful for inspecting extraction results before running full ingestion.
    """
    try:
        from app.parsing.multimodal_parser import MultimodalPDFParser

        # Read uploaded file
        file_data = await file.read()
        file_name = file.filename

        # Parse
        parser = MultimodalPDFParser()
        results = parser.parse(file_data, file_name)

        # Convert to response (strip raw image bytes)
        pages = []
        for page_data in results:
            images = []
            for img in page_data["images"]:
                images.append(ExtractImageInfo(
                    bbox=list(img["bbox"]) if img.get("bbox") else None,
                    format=img["format"],
                    width=img["width"],
                    height=img["height"],
                    hash=img.get("hash", ""),
                    image_type=img["image_type"].value if hasattr(img["image_type"], "value") else str(img["image_type"]),
                    surrounding_text=img.get("surrounding_text", ""),
                ))
            pages.append(ExtractPageResult(
                page=page_data["page"],
                text=page_data["text"],
                images=images,
                role=page_data["role"],
            ))

        total_images = sum(len(p.images) for p in pages)

        return ExtractResponse(
            status="success",
            filename=file_name,
            total_pages=len(pages),
            total_images=total_images,
            pages=pages,
        )

    except Exception as e:
        logger.error(f"Failed to extract document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {str(e)}",
        )


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "indexing",
        "version": "1.0.0",
    }
