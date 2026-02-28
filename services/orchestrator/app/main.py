"""Orchestrator Service - Main application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn

from app.api.routes import router
from app.config import settings
from app.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    # Startup
    logger.info("Starting Orchestrator Service")
    logger.info(f"Indexing Service URL: {settings.indexing_url}")
    logger.info(f"Agent Service URL: {settings.agent_url}")
    logger.info(f"MinIO Endpoint: {settings.minio_endpoint}")

    yield

    # Shutdown
    logger.info("Shutting down Orchestrator Service")


app = FastAPI(
    title="Orchestrator Service",
    description="User entry point for RAG system - orchestrates Indexing and Agent services",
    version="0.1.0",
    lifespan=lifespan,
)

# Include routes
app.include_router(router)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
