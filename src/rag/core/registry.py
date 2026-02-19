"""
组件注册中心 (ComponentRegistry)。

使用装饰器模式注册可插拔组件，按名称查找。
替代原 factory.py 中的 if/elif 策略路由。

用法示例:
    @ComponentRegistry.chunker("fixed")
    class FixedChunker(BaseChunker):
        ...

    # 运行时按名称获取
    chunker = ComponentRegistry.get_chunker("fixed")
"""

from __future__ import annotations

from typing import Type

from rag.core.types import (
    BaseChunker,
    BaseLLMProvider,
    BaseEmbeddingProvider,
    BaseRerankerProvider,
)


class ComponentRegistry:
    """全局组件注册中心。所有组件通过装饰器自注册。"""

    _chunkers: dict[str, Type[BaseChunker]] = {}
    _llm_providers: dict[str, Type[BaseLLMProvider]] = {}
    _embedding_providers: dict[str, Type[BaseEmbeddingProvider]] = {}
    _reranker_providers: dict[str, Type[BaseRerankerProvider]] = {}

    # --- 切片策略 ---

    @classmethod
    def chunker(cls, name: str):
        """装饰器: 注册切片策略。"""
        def decorator(klass: Type[BaseChunker]):
            cls._chunkers[name] = klass
            return klass
        return decorator

    @classmethod
    def get_chunker(cls, name: str) -> BaseChunker:
        if name not in cls._chunkers:
            available = list(cls._chunkers.keys())
            raise ValueError(
                f"Unknown chunker '{name}'. Available: {available}"
            )
        return cls._chunkers[name]()

    @classmethod
    def list_chunkers(cls) -> list[str]:
        return list(cls._chunkers.keys())

    # --- LLM 供应商 ---

    @classmethod
    def llm_provider(cls, name: str):
        """装饰器: 注册 LLM 供应商。"""
        def decorator(klass: Type[BaseLLMProvider]):
            cls._llm_providers[name] = klass
            return klass
        return decorator

    @classmethod
    def get_llm_provider(cls, name: str) -> BaseLLMProvider:
        if name not in cls._llm_providers:
            available = list(cls._llm_providers.keys())
            raise ValueError(
                f"Unknown LLM provider '{name}'. Available: {available}"
            )
        return cls._llm_providers[name]()

    # --- Embedding 供应商 ---

    @classmethod
    def embedding_provider(cls, name: str):
        """装饰器: 注册 Embedding 供应商。"""
        def decorator(klass: Type[BaseEmbeddingProvider]):
            cls._embedding_providers[name] = klass
            return klass
        return decorator

    @classmethod
    def get_embedding_provider(cls, name: str) -> BaseEmbeddingProvider:
        if name not in cls._embedding_providers:
            available = list(cls._embedding_providers.keys())
            raise ValueError(
                f"Unknown embedding provider '{name}'. Available: {available}"
            )
        return cls._embedding_providers[name]()

    # --- Reranker 供应商 ---

    @classmethod
    def reranker_provider(cls, name: str):
        """装饰器: 注册 Reranker 供应商。"""
        def decorator(klass: Type[BaseRerankerProvider]):
            cls._reranker_providers[name] = klass
            return klass
        return decorator

    @classmethod
    def get_reranker_provider(cls, name: str) -> BaseRerankerProvider:
        if name not in cls._reranker_providers:
            available = list(cls._reranker_providers.keys())
            raise ValueError(
                f"Unknown reranker provider '{name}'. Available: {available}"
            )
        return cls._reranker_providers[name]()
