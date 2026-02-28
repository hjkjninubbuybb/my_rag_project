"""
Agent 工具工厂。

修改版：通过 HTTP 调用 Indexing Service 的检索 API，不直接访问数据库。
"""

from typing import List, Tuple
import httpx

from langchain_core.tools import tool, BaseTool

from app.config import service_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


def get_tools(config: dict) -> List[BaseTool]:
    """根据实验配置创建检索工具列表。

    Args:
        config: 实验配置字典（从 ChatRequest.config 传入）

    Returns:
        工具列表
    """

    @tool(response_format="content_and_artifact")
    def knowledge_base_search(query: str) -> Tuple[str, List[dict]]:
        """检索知识库并返回相关文档片段。

        通过调用 Indexing Service 的 /api/v1/retrieve 端点进行检索。

        Args:
            query: 检索查询文本

        Returns:
            (content, artifact) tuple:
            - content: 用于 Agent 推理的文本内容
            - artifact: 调试数据（传递给前端显示）
        """
        try:
            # 调用 Indexing Service 检索 API
            response = httpx.post(
                f"{service_settings.indexing_url}/api/v1/retrieve",
                json={
                    "query": query,
                    "config": config,
                    "top_k": config.get("retrieval_top_k", 5),
                },
                timeout=30.0,
            )

            if response.status_code != 200:
                logger.error(f"Indexing Service 检索失败: {response.status_code} {response.text}")
                return "检索服务暂时不可用，请稍后重试。", []

            result = response.json()
            nodes = result.get("nodes", [])

            if not nodes:
                return "未找到相关文档。", []

            # content: 用于 Agent 推理
            content = "\n\n".join([
                f"文档片段 {i+1}:\n{node['text']}"
                for i, node in enumerate(nodes)
            ])

            # artifact: 调试数据（传递给前端）
            artifact = [
                {
                    "text": node["text"][:500],  # 截断显示
                    "score": node.get("score", 0.0),
                    "source_file": node.get("metadata", {}).get("file_name", "unknown"),
                }
                for node in nodes
            ]

            logger.info(f"检索成功: query='{query}', 返回 {len(nodes)} 个结果")
            return content, artifact

        except httpx.TimeoutException:
            logger.error("Indexing Service 检索超时")
            return "检索服务响应超时，请稍后重试。", []
        except Exception as e:
            logger.error(f"检索失败: {e}")
            return f"检索过程中发生错误: {str(e)}", []

    return [knowledge_base_search]
