"""DashScope VLM Provider（视觉语言模型）。

用于图像摘要生成和多模态推理。
"""

import base64
import requests
from typing import List, Optional

from app.core.registry import ComponentRegistry
from app.core.types import BaseVLMProvider, ImageType
from app.utils.logger import get_logger

logger = get_logger(__name__)


@ComponentRegistry.vlm_provider("dashscope")
class DashScopeVLMProvider(BaseVLMProvider):
    """阿里云 DashScope VLM Provider（基于 Qwen-VL 系列）。

    支持的模型：
    - qwen-vl-max: 最强多模态模型
    - qwen-vl-plus: 平衡性能和成本
    """

    API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

    def __init__(self, api_key: str, model_name: str = "qwen-vl-max"):
        """初始化 VLM Provider。

        Args:
            api_key: DashScope API Key。
            model_name: 模型名称，默认 qwen-vl-max。
        """
        self.api_key = api_key
        self.model_name = model_name
        logger.info(f"DashScopeVLMProvider 初始化完成，模型: {model_name}")

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
        # 构建针对不同图片类型的 prompt
        prompt = self._build_summary_prompt(image_type, surrounding_text)

        # 将图片转换为 base64
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

        # 构建 OpenAI 格式的消息
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                        }
                    ]
                }
            ],
            "temperature": kwargs.get("temperature", 0.1),  # 低温度保证准确性
            "max_tokens": kwargs.get("max_tokens", 1000),
        }

        try:
            response = requests.post(
                self.API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                summary = data["choices"][0]["message"]["content"]
                logger.debug(
                    f"图像摘要生成成功，类型: {image_type.value}, "
                    f"摘要长度: {len(summary)} 字符"
                )
                return summary
            else:
                raise RuntimeError(
                    f"VLM 调用失败: HTTP {response.status_code}, "
                    f"响应: {response.text}"
                )

        except Exception as e:
            logger.error(f"图像摘要生成失败: {e}")
            raise

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
        # 构建多模态消息内容
        content = []

        # 添加文本 prompt
        prompt = self._build_generation_prompt(query, text_context)
        content.append({"type": "text", "text": prompt})

        # 添加所有图片
        for img_bytes in images:
            image_base64 = base64.b64encode(img_bytes).decode('utf-8')
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
            })

        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": content}],
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2000),
        }

        try:
            response = requests.post(
                self.API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60
            )

            if response.status_code == 200:
                data = response.json()
                answer = data["choices"][0]["message"]["content"]
                logger.debug(f"VLM 生成答案成功，长度: {len(answer)} 字符")
                return answer
            else:
                raise RuntimeError(
                    f"VLM 生成失败: HTTP {response.status_code}, "
                    f"响应: {response.text}"
                )

        except Exception as e:
            logger.error(f"VLM 生成失败: {e}")
            raise

    def _build_summary_prompt(
        self,
        image_type: ImageType,
        surrounding_text: Optional[str]
    ) -> str:
        """构建图像摘要的 prompt（针对不同图片类型）。"""

        base_instruction = "你是一个教务信息提取专家。请详细描述这张图片的内容。"

        # 根据图片类型定制 prompt
        type_specific_instructions = {
            ImageType.SCREENSHOT: (
                "这是一个系统界面截图。请描述：\n"
                "1. 界面的主要功能和用途\n"
                "2. 所有可见的按钮、菜单、输入框及其标签\n"
                "3. 界面元素的位置关系和操作流程\n"
                "4. 任何提示信息或说明文字"
            ),
            ImageType.FLOWCHART: (
                "这是一个流程图。请描述：\n"
                "1. 按顺序列出所有步骤和节点\n"
                "2. 每个步骤涉及的审核部门或角色\n"
                "3. 决策节点的条件和分支\n"
                "4. 流程的起点和终点"
            ),
            ImageType.TABLE: (
                "这是一个表格。请描述：\n"
                "1. 表格的标题和用途\n"
                "2. 所有列的表头名称\n"
                "3. 关键数据的规律和范围\n"
                "4. 任何特殊标注或说明"
            ),
            ImageType.DIAGRAM: (
                "这是一个图表。请描述：\n"
                "1. 图表的类型和用途\n"
                "2. 所有组成部分及其关系\n"
                "3. 关键的标签和数值\n"
                "4. 图表要表达的核心信息"
            ),
            ImageType.OTHER: (
                "请详细描述这张图片的内容，包括：\n"
                "1. 图片的主要内容和用途\n"
                "2. 所有可见的文字信息\n"
                "3. 重要的视觉元素"
            )
        }

        instruction = type_specific_instructions.get(
            image_type,
            type_specific_instructions[ImageType.OTHER]
        )

        # 添加周围文本作为上下文
        context_part = ""
        if surrounding_text:
            context_part = f"\n\n图片周围的文本（作为上下文参考）：\n{surrounding_text}\n"

        # 组装完整 prompt
        prompt = f"""{base_instruction}

{instruction}

要求：
- 必须包含所有关键的专有名词、部门名称、数值
- 输出纯文本，不要使用 Markdown 格式
- 描述要详尽，确保后续检索能够准确匹配
{context_part}"""

        return prompt

    def _build_generation_prompt(self, query: str, text_context: str) -> str:
        """构建多模态生成的 prompt。"""

        prompt = f"""你是一个教务系统助手。请根据提供的文本信息和图片，回答用户的问题。

用户问题：
{query}

相关文本信息：
{text_context}

请仔细查看图片中的内容，结合文本信息，给出准确、详细的回答。如果图片中包含流程图或表格，请按照图片中的实际内容进行说明。"""

        return prompt
