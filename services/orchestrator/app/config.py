"""Configuration for Orchestrator Service."""
from pydantic_settings import BaseSettings


class ServiceSettings(BaseSettings):
    """Service configuration."""

    # Service URLs
    indexing_url: str = "http://indexing:8001"
    agent_url: str = "http://agent:8002"

    # MinIO
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Timeouts (seconds)
    indexing_timeout: float = 300.0
    agent_timeout: float = 300.0

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = ServiceSettings()
