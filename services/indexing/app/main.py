"""FastAPI application for Indexing Service."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.config import settings
from app.api import routes
from app.storage.vectordb import VectorStoreManager
from app.storage.mysql_client import MySQLClient
from app.utils.logger import logger

# Import all components to trigger registration
import app.components  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    # Startup
    logger.info("Starting Indexing Service...")

    # Initialize storage clients
    logger.info("Initializing storage clients...")

    # Qdrant
    vector_store = VectorStoreManager(
        qdrant_url=settings.qdrant_url,
        qdrant_path=settings.qdrant_path,
    )
    logger.info(f"Connected to Qdrant: {settings.qdrant_url or settings.qdrant_path}")

    # MySQL
    mysql_client = MySQLClient(connection_url=settings.mysql_url)
    logger.info(f"Connected to MySQL: {settings.mysql_host}:{settings.mysql_port}")

    # Set clients in routes module
    routes.vector_store = vector_store
    routes.mysql_client = mysql_client

    logger.info("Indexing Service started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Indexing Service...")


# Create FastAPI app
app = FastAPI(
    title="Indexing Service",
    description="Document indexing and retrieval service for RAG system",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(routes.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "indexing",
        "version": "1.0.0",
        "status": "running",
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=True,
    )
