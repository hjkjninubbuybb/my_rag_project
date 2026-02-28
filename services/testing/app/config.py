"""Configuration for Testing Service."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Testing Service settings."""

    # Service
    service_name: str = "testing"
    service_port: int = 8003

    # MySQL
    mysql_url: str = "mysql+pymysql://rag_user:rag_password@localhost:3306/rag_db"

    # Service URLs
    orchestrator_url: str = "http://localhost:8000"
    indexing_url: str = "http://localhost:8001"
    agent_url: str = "http://localhost:8002"

    # Test data
    test_documents_dir: str = "app/data/test_documents"
    test_queries_file: str = "app/data/test_queries.json"

    class Config:
        env_file = ".env"


settings = Settings()
