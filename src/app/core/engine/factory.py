from functools import lru_cache
from typing import Optional

from llama_index.llms.dashscope import DashScope
from llama_index.embeddings.dashscope import DashScopeEmbedding
from llama_index.core.llms import LLM
from llama_index.core.base.embeddings.base import BaseEmbedding

from app.settings import settings


class ModelFactory:
    """
    模型工厂：负责创建连接阿里云百炼的模型实例
    """

    @staticmethod
    @lru_cache(maxsize=1)
    def get_llm(api_key: Optional[str] = None) -> LLM:
        """获取 Qwen LLM"""
        # 优先使用传入的 Key，否则使用全局配置的 Key
        key = api_key or settings.dashscope_api_key
        if not key:
            raise ValueError("API Key is missing. Please check .env or pass it explicitly.")

        return DashScope(
            model_name=settings.llm_model,
            api_key=key,
            temperature=0.0  # RAG 任务保持严谨
        )

    @staticmethod
    @lru_cache(maxsize=1)
    def get_embedding(api_key: Optional[str] = None) -> BaseEmbedding:
        """获取 Qwen Embedding"""
        key = api_key or settings.dashscope_api_key
        if not key:
            raise ValueError("API Key is missing for Embedding.")

        return DashScopeEmbedding(
            model_name=settings.embedding_model,
            api_key=key
        )