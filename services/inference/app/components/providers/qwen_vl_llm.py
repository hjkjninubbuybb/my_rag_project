"""Qwen-VL 多模态 LLM Provider。

使用 DashScope 兼容模式 API 调用 qwen-vl-max。
"""

from typing import List

try:
    from langchain_community.chat_models.tongyi import ChatTongyi
    from langchain_core.messages import HumanMessage
except ImportError:
    raise ImportError(
        "LangChain Community is required for Qwen-VL LLM. "
        "Install: pip install langchain-community"
    )

from rag_shared.core.registry import ComponentRegistry
from rag_shared.core.types import BaseMultimodalLLMProvider
from rag_shared.utils.logger import get_logger

logger = get_logger(__name__)


@ComponentRegistry.multimodal_llm_provider("qwen-vl")
class QwenVLLLMProvider(BaseMultimodalLLMProvider):
    """Qwen-VL 多模态 LLM Provider（使用 LangChain）。"""

    def create_multimodal_llm(
        self, model_name: str, api_key: str, **kwargs
    ):
        """创建支持图像输入的 LLM 实例。

        Args:
            model_name: 模型名称（如 "qwen-vl-max"）。
            api_key: DashScope API Key。
            **kwargs: 额外参数（如 temperature）。

        Returns:
            ChatTongyi 实例（支持多模态输入）。
        """
        temperature = kwargs.get("temperature", 0.1)

        llm = ChatTongyi(
            model=model_name,
            dashscope_api_key=api_key,
            temperature=temperature,
        )

        logger.info(f"QwenVLLLMProvider 初始化: model={model_name}")
        return llm

    @staticmethod
    def create_multimodal_message(
        text: str, images: List[str]
    ) -> HumanMessage:
        """创建多模态消息（文本 + base64 图片）。

        Args:
            text: 文本内容。
            images: base64 编码的图片列表。

        Returns:
            HumanMessage 实例（支持多模态内容）。
        """
        content = [{"type": "text", "text": text}]

        for img_b64 in images:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
            })

        return HumanMessage(content=content)
