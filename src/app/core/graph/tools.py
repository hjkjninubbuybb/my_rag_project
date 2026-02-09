from functools import lru_cache
from typing import List
from langchain_core.tools import BaseTool

from app.core.engine.retrieval import RetrievalService

@lru_cache(maxsize=1)
def get_search_tool() -> BaseTool:
    """
    工厂方法：获取检索工具
    使用 lru_cache 确保全局只初始化一次 RetrievalService
    """
    service = RetrievalService()
    return service.as_langchain_tool()

def get_tools() -> List[BaseTool]:
    """返回所有可用工具列表"""
    return [get_search_tool()]