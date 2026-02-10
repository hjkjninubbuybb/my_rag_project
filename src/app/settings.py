import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 基础配置
    app_name: str = "Agentic RAG"
    debug: bool = True

    # 模型配置
    llm_model: str = "qwen-plus"
    embedding_model: str = "text-embedding-v4"

    # 阿里云 API Key
    dashscope_api_key: str | None = None

    # Qdrant 配置
    qdrant_path: str = "qdrant_db"
    embedding_dim: int = 1536  # ✅ 新增：text-embedding-v4 的向量维度

    # RAG 切片配置
    chunk_size_parent: int = 1024
    chunk_size_child: int = 256

    # 检索与重排序配置
    retrieval_top_k: int = 50  # 初筛: 从向量库取回多少条
    rerank_top_k: int = 5      # 重排: 精排后给大模型看多少条

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()