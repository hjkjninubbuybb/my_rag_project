"""
LangGraph Agent 工作流。

修改版：不依赖 ExperimentConfig 和 ComponentRegistry，直接使用配置字典。

图结构:
  START → summarize → analyze_rewrite → route → [process_question x N] → aggregate → END
"""

from functools import partial

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Send
from langchain_community.chat_models.tongyi import ChatTongyi

from app.agent.state import State, AgentState
from app.agent.tools import get_tools
from app.agent.nodes import (
    analyze_chat_and_summarize,
    analyze_and_rewrite_query,
    agent_node,
    extract_final_answer,
    aggregate_responses,
)
from app.config import service_settings


# --- 路由逻辑 ---
def route_after_rewrite(state: State) -> list[Send]:
    """将每个子问题分发到独立的 Agent 子图并行处理。"""
    return [
        Send("process_question", {
            "question": q,
            "question_index": i,
            "messages": [],
        })
        for i, q in enumerate(state.get("rewrittenQuestions", []))
    ]


# --- 构建图 ---
def create_graph(config: dict):
    """根据配置字典构建 LangGraph Agent 工作流。

    Args:
        config: 配置字典，包含 llm_model, dashscope_api_key, temperature 等

    Returns:
        编译后的 LangGraph 实例
    """

    # 创建 LLM（使用 DashScope/Qwen）
    llm_model = config.get("llm_model", "qwen-plus")
    api_key = config.get("dashscope_api_key", service_settings.dashscope_api_key)
    temperature = config.get("llm_temperature", 0.1)

    ctrl_llm = ChatTongyi(
        model=llm_model,
        dashscope_api_key=api_key,
        temperature=temperature,
    )

    tools = get_tools(config)
    llm_with_tools = ctrl_llm.bind_tools(tools)

    # 子图 (Agent Subgraph - ReAct 循环)
    agent_builder = StateGraph(AgentState)
    agent_builder.add_node("agent", partial(agent_node, llm_with_tools=llm_with_tools, config=config))
    agent_builder.add_node("tools", ToolNode(tools))
    agent_builder.add_node("extract_answer", extract_final_answer)

    agent_builder.add_edge(START, "agent")
    agent_builder.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: "extract_answer"})
    agent_builder.add_edge("tools", "agent")
    agent_builder.add_edge("extract_answer", END)

    agent_subgraph = agent_builder.compile()

    # 主图 (Main Graph)
    workflow = StateGraph(State)
    workflow.add_node("summarize", partial(analyze_chat_and_summarize, llm=ctrl_llm))
    workflow.add_node("analyze_rewrite", partial(analyze_and_rewrite_query, llm=ctrl_llm))
    workflow.add_node("process_question", agent_subgraph)
    workflow.add_node("aggregate", partial(aggregate_responses, llm=ctrl_llm))

    workflow.add_edge(START, "summarize")
    workflow.add_edge("summarize", "analyze_rewrite")
    workflow.add_conditional_edges("analyze_rewrite", route_after_rewrite)
    workflow.add_edge("process_question", "aggregate")
    workflow.add_edge("aggregate", END)

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)
