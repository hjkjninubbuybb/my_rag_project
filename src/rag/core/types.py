"""
核心抽象基类定义。

所有可插拔组件必须实现对应接口。
添加新策略或供应商时，只需创建新文件并实现这些接口，
然后通过 ComponentRegistry 注册即可。
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseChunker(ABC):
    """切片策略接口。"""

    @abstractmethod
    def create_splitter(self, chunk_size: int, chunk_overlap: int) -> Any:
        """创建并返回一个 NodeParser 实例。"""
        ...


class BaseLLMProvider(ABC):
    """LLM 供应商接口。"""

    @abstractmethod
    def create_llm(self, model_name: str, api_key: str, temperature: float, **kwargs) -> Any:
        """创建并返回一个 LlamaIndex LLM 实例（用于检索管线）。"""
        ...

    @abstractmethod
    def create_chat_model(self, model_name: str, api_key: str, temperature: float, **kwargs) -> Any:
        """创建并返回一个 LangChain BaseChatModel 实例（用于 Agent 工作流）。"""
        ...


class BaseEmbeddingProvider(ABC):
    """Embedding 供应商接口。"""

    @abstractmethod
    def create_embedding(self, model_name: str, api_key: str, **kwargs) -> Any:
        """创建并返回一个 Embedding 模型实例。"""
        ...


class BaseRerankerProvider(ABC):
    """Reranker 供应商接口。"""

    @abstractmethod
    def create_reranker(self, model_name: str, api_key: str, top_n: int, **kwargs) -> Any:
        """创建并返回一个 Reranker 实例。"""
        ...
