"""DashScope Embedding 供应商（文本 + 多模态）。"""

import os
import tempfile
from typing import List
from pathlib import Path

from llama_index.embeddings.openai import OpenAIEmbedding

try:
    import dashscope
except ImportError:
    raise ImportError(
        "DashScope SDK is required for Qwen-VL embedding. "
        "Install: pip install dashscope"
    )

from app.core.registry import ComponentRegistry
from app.core.types import BaseEmbeddingProvider, BaseMultimodalEmbeddingProvider
from app.utils.logger import get_logger

logger = get_logger(__name__)


@ComponentRegistry.embedding_provider("dashscope")
class DashScopeEmbeddingProvider(BaseEmbeddingProvider):
    """阿里云 DashScope Embedding 供应商 (通过 OpenAI 兼容接口)。"""

    def create_embedding(self, model_name: str, api_key: str, **kwargs):
        return OpenAIEmbedding(
            model_name=model_name,
            api_key=api_key,
            api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            embed_batch_size=10,
        )


@ComponentRegistry.multimodal_embedding_provider("qwen-vl")
class QwenVLEmbeddingProvider(BaseMultimodalEmbeddingProvider):
    """Qwen-VL 多模态 Embedding Provider（使用 DashScope SDK）。

    基于 POC 测试结果（2026-02-26）：
    - 模型名称: qwen3-vl-embedding
    - Embedding 维度: 2560
    - API 调用方式: dashscope.MultiModalEmbedding.call()
    """

    def __init__(self, api_key: str):
        """初始化 Provider。

        Args:
            api_key: DashScope API Key。
        """
        dashscope.api_key = api_key
        logger.info("QwenVLEmbeddingProvider 初始化完成")

    def embed_images(self, image_paths: List[str], **kwargs) -> List[List[float]]:
        """批量图像 embedding。

        Args:
            image_paths: 图片文件路径列表（本地路径）。
            **kwargs: 额外参数（当前未使用）。

        Returns:
            embeddings: 2560 维向量列表。

        Raises:
            RuntimeError: 如果 API 调用失败。
        """
        embeddings = []

        for image_path in image_paths:
            # DashScope SDK 需要 file:// 协议的绝对路径
            abs_path = os.path.abspath(image_path)
            input_data = [{"image": f"file://{abs_path}"}]

            try:
                resp = dashscope.MultiModalEmbedding.call(
                    model="qwen3-vl-embedding",  # POC 确认的模型名称
                    input=input_data
                )

                if resp.status_code == 200:
                    embedding = resp.output["embeddings"][0]["embedding"]
                    embeddings.append(embedding)
                    logger.debug(
                        f"图像 embedding 成功: {Path(image_path).name}, "
                        f"维度: {len(embedding)}"
                    )
                else:
                    raise RuntimeError(
                        f"Embedding failed: {resp.message}, "
                        f"request_id: {resp.request_id}"
                    )

            except Exception as e:
                logger.error(f"图像 embedding 失败: {image_path}, 错误: {e}")
                raise

        logger.info(f"批量图像 embedding 完成: {len(embeddings)} 张图片")
        return embeddings

    def embed_images_from_bytes(
        self, images: List[bytes], **kwargs
    ) -> List[List[float]]:
        """从图像 bytes 数据生成 embedding（需要临时保存文件）。

        Args:
            images: 图片二进制数据列表。
            **kwargs: 额外参数。

        Returns:
            embeddings: 2560 维向量列表。
        """
        embeddings = []
        temp_files = []

        try:
            # 保存到临时文件
            for img_bytes in images:
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".jpg", delete=False, mode="wb"
                )
                tmp.write(img_bytes)
                tmp.close()
                temp_files.append(tmp.name)

            # 批量调用
            embeddings = self.embed_images(temp_files)

        finally:
            # 清理临时文件
            for tmp_path in temp_files:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception as e:
                    logger.warning(f"清理临时文件失败: {tmp_path}, 错误: {e}")

        return embeddings

    def get_embedding_dim(self) -> int:
        """返回图像 embedding 维度。

        Returns:
            2560（POC 确认的维度）。
        """
        return 2560
