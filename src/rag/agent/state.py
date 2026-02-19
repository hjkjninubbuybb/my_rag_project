import operator
from typing import Annotated, Any, List, TypedDict
from langgraph.graph import MessagesState
from langchain_core.messages import BaseMessage


def accumulate_or_reset(existing: list[dict], new: list[dict]) -> list[dict]:
    """
    Reducer函数：处理并行Agent返回的答案
    如果新数据包含 '__reset__' 标志，则清空列表
    """
    if new and any(item.get("__reset__") for item in new):
        return []
    return existing + new


class State(MessagesState):
    """
    主图状态 (Main Graph State)
    继承自 MessagesState，自带 'messages' 字段
    """
    questionIsClear: bool
    conversation_summary: str
    originalQuery: str
    rewrittenQuestions: list[str]

    # 使用 Annotated 定义 Reducer，实现 Map-Reduce 的结果收集
    agent_answers: Annotated[list[dict], accumulate_or_reset]

    # 检索调试数据：物理分块原文、Score、来源文件
    debug_retrieved_chunks: Annotated[list[dict], operator.add]


class AgentState(MessagesState):
    """
    子图状态 (Agent Subgraph State)
    用于单个 Agent 的 ReAct 循环
    """
    question: str
    question_index: int
    final_answer: str
    agent_answers: list[dict]
    debug_retrieved_chunks: list[dict]