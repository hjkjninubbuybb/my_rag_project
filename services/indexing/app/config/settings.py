"""Service configuration for Indexing Service."""

import os
from pydantic_settings import BaseSettings


class ServiceSettings(BaseSettings):
    """Indexing Service configuration."""

    # Service
    service_name: str = "indexing"
    service_port: int = 8001
    service_host: str = "0.0.0.0"

    # Qdrant
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_path: str = os.getenv("QDRANT_PATH", "data/vectordb")

    # MySQL
    mysql_url: str = os.getenv(
        "MYSQL_URL",
        "mysql+pymysql://rag_user:rag_password@localhost:3306/rag_db"
    )
    mysql_host: str = os.getenv("MYSQL_HOST", "localhost")
    mysql_port: int = int(os.getenv("MYSQL_PORT", "3306"))
    mysql_user: str = os.getenv("MYSQL_USER", "rag_user")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "rag_password")
    mysql_database: str = os.getenv("MYSQL_DATABASE", "rag_db")

    # DashScope API
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")

    # Data directories (for local development, not used in production)
    policy_data_dir: str = "data/uploads/policy"
    manual_data_dir: str = "data/uploads/manual"

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = ServiceSettings()
