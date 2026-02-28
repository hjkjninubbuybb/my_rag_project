"""
核心抽象基类定义。

所有可插拔组件必须实现对应接口。
添加新策略或供应商时，只需创建新文件并实现这些接口，
然后通过 ComponentRegistry 注册即可。
"""

from abc import ABC, abstractmethod
from typing import Any, List, Dict, Optional
from enum import Enum


# ──────────────────── 枚举类型 ────────────────────


class ImageType(str, Enum):
    """图片类型枚举（用于多模态解析）。"""

    SCREENSHOT = "screenshot"      # 系统截图（界面元素、按钮）
    FLOWCHART = "flowchart"        # 流程图（审批流程、操作步骤）
    TABLE = "table"                # 表格截图（学分表、数据统计）
    DIAGRAM = "diagram"            # 其他图表（架构图、关系图）
    OTHER = "other"                # 未分类图片


# ──────────────────── 基础组件接口 ────────────────────


class BaseChunker(ABC):
    """切片策略接口。"""

    @abstractmethod
    def create_splitter(self, chunk_size: int, chunk_overlap: int, **kwargs) -> Any:
        """创建并返回一个 NodeParser 实例。

        Args:
            chunk_size: 目标切片大小（token 或字符数）。
            chunk_overlap: 切片重叠大小。
            **kwargs: 额外参数（如 embed_model），由具体策略按需使用。
        """
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


# ──────────────────── 多模态抽象基类 ────────────────────


class BaseMultimodalEmbeddingProvider(ABC):
    """多模态 Embedding 供应商接口。"""

    @abstractmethod
    def embed_images(self, image_paths: List[str], **kwargs) -> List[List[float]]:
        """批量图像 embedding。

        Args:
            image_paths: 图片文件路径列表（本地路径）。
            **kwargs: 额外参数。

        Returns:
            embeddings: 向量列表，每个向量为 List[float]。
        """
        ...

    @abstractmethod
    def get_embedding_dim(self) -> int:
        """返回图像 embedding 维度。"""
        ...


class BaseMultimodalLLMProvider(ABC):
    """多模态 LLM 供应商接口。"""

    @abstractmethod
    def create_multimodal_llm(self, model_name: str, api_key: str, **kwargs) -> Any:
        """创建支持图像输入的 LLM 实例。

        Args:
            model_name: 多模态模型名称（如 qwen-vl-max）。
            api_key: API 密钥。
            **kwargs: 额外参数（如 temperature）。

        Returns:
            多模态 LLM 实例（通常是 LangChain ChatModel）。
        """
        ...


class BaseImageProcessor(ABC):
    """图像处理组件接口。"""

    @abstractmethod
    def preprocess(self, image_bytes: bytes, **kwargs) -> bytes:
        """预处理图像：压缩、裁剪、格式转换。

        Args:
            image_bytes: 原始图像二进制数据。
            **kwargs: 处理参数（如 max_size, quality）。

        Returns:
            处理后的图像二进制数据。
        """
        ...

    @abstractmethod
    def extract_hash(self, image_bytes: bytes) -> str:
        """计算图像内容 hash（用于去重）。

        Args:
            image_bytes: 图像二进制数据。

        Returns:
            Hash 字符串（如 MD5）。
        """
        ...


class BaseVLMProvider(ABC):
    """视觉语言模型（VLM）供应商接口。

    用于图像摘要生成和多模态推理。
    """

    @abstractmethod
    def generate_image_summary(
        self,
        image_bytes: bytes,
        image_type: ImageType,
        surrounding_text: Optional[str] = None,
        **kwargs
    ) -> str:
        """为图片生成详细的文本摘要。

        Args:
            image_bytes: 图像二进制数据。
            image_type: 图片类型（用于选择合适的 prompt）。
            surrounding_text: 图片周围的文本（提供上下文）。
            **kwargs: 额外参数（如 temperature, max_tokens）。

        Returns:
            详细的文本摘要，包含所有关键专业名词。
        """
        ...

    @abstractmethod
    def generate_with_images(
        self,
        query: str,
        text_context: str,
        images: List[bytes],
        **kwargs
    ) -> str:
        """基于文本上下文和图片生成答案。

        Args:
            query: 用户问题。
            text_context: 检索到的文本上下文。
            images: 图片二进制数据列表。
            **kwargs: 额外参数（如 temperature）。

        Returns:
            生成的答案文本。
        """
        ...
