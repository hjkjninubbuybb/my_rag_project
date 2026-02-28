"""VLM 分析服务。

提供图像分析和摘要生成能力，供 Indexing Service 调用。
"""

import base64
import requests
from typing import Optional, List, Dict, Any

from app.utils.logger import get_logger

logger = get_logger(__name__)


class VLMService:
    """VLM 服务（基于 DashScope Qwen-VL）。"""

    API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

    def __init__(self, api_key: str, model_name: str = "qwen-vl-max"):
        """初始化 VLM 服务。

        Args:
            api_key: DashScope API Key
            model_name: VLM 模型名称（默认 qwen-vl-max）
        """
        self.api_key = api_key
        self.model_name = model_name
        logger.info(f"VLMService 初始化完成，模型: {model_name}")

    def analyze_image(
        self,
        image_base64: str,
        image_type: str = "screenshot",
        surrounding_text: Optional[str] = None,
        prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """分析单张图像并生成摘要。

        Args:
            image_base64: Base64 编码的图像
            image_type: 图像类型（screenshot, flowchart, table, diagram, other）
            surrounding_text: 图像周围的上下文文本
            prompt: 自定义 prompt（如果为 None，则根据 image_type 自动生成）
            **kwargs: 额外参数（temperature, max_tokens）

        Returns:
            图像摘要文本
        """
        if prompt is None:
            prompt = self._build_summary_prompt(image_type, surrounding_text)

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
            "temperature": kwargs.get("temperature", 0.1),
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
                logger.debug(f"图像分析成功，类型: {image_type}, 摘要长度: {len(summary)} 字符")
                return summary
            else:
                raise RuntimeError(
                    f"VLM 调用失败: HTTP {response.status_code}, 响应: {response.text}"
                )

        except Exception as e:
            logger.error(f"图像分析失败: {e}")
            raise

    def batch_summarize(
        self,
        images: List[Dict[str, Any]],
        **kwargs
    ) -> List[str]:
        """批量图像摘要。

        Args:
            images: 图像列表，每个包含 base64, type, surrounding_text
            **kwargs: 额外参数

        Returns:
            摘要列表
        """
        summaries = []
        for img in images:
            try:
                summary = self.analyze_image(
                    image_base64=img.get("base64", ""),
                    image_type=img.get("type", "screenshot"),
                    surrounding_text=img.get("surrounding_text"),
                    **kwargs
                )
                summaries.append(summary)
            except Exception as e:
                logger.error(f"批量摘要失败（跳过该图像）: {e}")
                summaries.append(f"[摘要生成失败: {str(e)}]")

        return summaries

    def _build_summary_prompt(self, image_type: str, surrounding_text: Optional[str] = None) -> str:
        """构建图像摘要的 prompt。"""

        base_instruction = (
            "请详细描述这张图片的内容。你的描述将用于后续的文本检索，"
            "因此必须包含所有关键信息、专有名词、数值等。"
        )

        # 根据图片类型定制指令
        type_specific_instructions = {
            "screenshot": (
                "这是一张系统操作截图。请描述：\n"
                "1. 页面的主要功能和布局\n"
                "2. 所有可见的按钮、输入框、下拉菜单等交互元素\n"
                "3. 页面上的所有文字内容（包括标题、标签、提示信息）\n"
                "4. 操作流程或步骤（如果可见）"
            ),
            "flowchart": (
                "这是一张流程图。请描述：\n"
                "1. 流程的起点和终点\n"
                "2. 每个步骤的名称和顺序\n"
                "3. 分支条件和判断逻辑\n"
                "4. 涉及的角色或部门"
            ),
            "table": (
                "这是一张表格。请描述：\n"
                "1. 表格的标题和用途\n"
                "2. 列名和行标题\n"
                "3. 关键数据和数值\n"
                "4. 表格传达的主要信息"
            ),
            "diagram": (
                "这是一张示意图。请描述：\n"
                "1. 图示的主题和目的\n"
                "2. 各个组成部分及其关系\n"
                "3. 标注的文字和说明\n"
                "4. 图示传达的核心概念"
            ),
            "other": (
                "请描述这张图片的：\n"
                "1. 主要内容和用途\n"
                "2. 所有可见的文字信息\n"
                "3. 重要的视觉元素"
            )
        }

        instruction = type_specific_instructions.get(image_type, type_specific_instructions["other"])

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
