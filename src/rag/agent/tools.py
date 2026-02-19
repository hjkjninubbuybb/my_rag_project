"""
Agent 工具工厂。

接收 ExperimentConfig 创建 RetrievalService 并转为 LangChain Tool。
"""

from typing import List

from langchain_core.tools import BaseTool

from rag.config.experiment import ExperimentConfig
from rag.pipeline.retrieval import RetrievalService


def get_tools(config: ExperimentConfig) -> List[BaseTool]:
    """根据实验配置创建检索工具列表。"""
    service = RetrievalService(config)
    return [service.as_debug_langchain_tool()]
