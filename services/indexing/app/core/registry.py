"""
组件注册中心 (ComponentRegistry)。

使用装饰器模式注册可插拔组件，按名称查找。

用法示例:
    @ComponentRegistry.chunker("fixed")
    class FixedChunker(BaseChunker):
        ...

    # 运行时按名称获取
    chunker = ComponentRegistry.get_chunker("fixed")
"""

from __future__ import annotations

from typing import Type

from app.core.types import (
    BaseChunker,
    BaseLLMProvider,
    BaseEmbeddingProvider,
    BaseRerankerProvider,
    BaseMultimodalEmbeddingProvider,
    BaseMultimodalLLMProvider,
    BaseImageProcessor,
    BaseVLMProvider,
)


class ComponentRegistry:
    """全局组件注册中心。所有组件通过装饰器自注册。"""

    _chunkers: dict[str, Type[BaseChunker]] = {}
    _llm_providers: dict[str, Type[BaseLLMProvider]] = {}
    _embedding_providers: dict[str, Type[BaseEmbeddingProvider]] = {}
    _reranker_providers: dict[str, Type[BaseRerankerProvider]] = {}
    _multimodal_embedding_providers: dict[str, Type[BaseMultimodalEmbeddingProvider]] = {}
    _multimodal_llm_providers: dict[str, Type[BaseMultimodalLLMProvider]] = {}
    _image_processors: dict[str, Type[BaseImageProcessor]] = {}
    _vlm_providers: dict[str, Type[BaseVLMProvider]] = {}

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

    # --- 多模态 Embedding 供应商 ---

    @classmethod
    def multimodal_embedding_provider(cls, name: str):
        """装饰器: 注册多模态 Embedding 供应商。"""
        def decorator(klass: Type[BaseMultimodalEmbeddingProvider]):
            cls._multimodal_embedding_providers[name] = klass
            return klass
        return decorator

    @classmethod
    def get_multimodal_embedding_provider(cls, name: str) -> Type[BaseMultimodalEmbeddingProvider]:
        if name not in cls._multimodal_embedding_providers:
            available = list(cls._multimodal_embedding_providers.keys())
            raise ValueError(
                f"Unknown multimodal embedding provider '{name}'. Available: {available}"
            )
        return cls._multimodal_embedding_providers[name]

    # --- 多模态 LLM 供应商 ---

    @classmethod
    def multimodal_llm_provider(cls, name: str):
        """装饰器: 注册多模态 LLM 供应商。"""
        def decorator(klass: Type[BaseMultimodalLLMProvider]):
            cls._multimodal_llm_providers[name] = klass
            return klass
        return decorator

    @classmethod
    def get_multimodal_llm_provider(cls, name: str) -> Type[BaseMultimodalLLMProvider]:
        if name not in cls._multimodal_llm_providers:
            available = list(cls._multimodal_llm_providers.keys())
            raise ValueError(
                f"Unknown multimodal LLM provider '{name}'. Available: {available}"
            )
        return cls._multimodal_llm_providers[name]

    # --- 图像处理器 ---

    @classmethod
    def image_processor(cls, name: str):
        """装饰器: 注册图像处理器。"""
        def decorator(klass: Type[BaseImageProcessor]):
            cls._image_processors[name] = klass
            return klass
        return decorator

    @classmethod
    def get_image_processor(cls, name: str) -> Type[BaseImageProcessor]:
        if name not in cls._image_processors:
            available = list(cls._image_processors.keys())
            raise ValueError(
                f"Unknown image processor '{name}'. Available: {available}"
            )
        return cls._image_processors[name]

    # --- VLM 供应商 ---

    @classmethod
    def vlm_provider(cls, name: str):
        """装饰器: 注册 VLM 供应商。"""
        def decorator(klass: Type[BaseVLMProvider]):
            cls._vlm_providers[name] = klass
            return klass
        return decorator

    @classmethod
    def get_vlm_provider(cls, name: str) -> Type[BaseVLMProvider]:
        if name not in cls._vlm_providers:
            available = list(cls._vlm_providers.keys())
            raise ValueError(
                f"Unknown VLM provider '{name}'. Available: {available}"
            )
        return cls._vlm_providers[name]
