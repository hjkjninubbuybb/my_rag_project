from functools import partial
from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Send

from app.core.engine.factory import ModelFactory
from app.core.graph.state import State, AgentState
from app.core.graph.tools import get_tools
from app.core.graph.nodes import (
    analyze_chat_and_summarize,
    analyze_and_rewrite_query,
    human_input_node,
    agent_node,
    extract_final_answer,
    aggregate_responses
)


# --- 路由逻辑 ---
def route_after_rewrite(state: State) -> Literal["human_input"] | list[Send]:
    """
    决定下一步：人工介入 OR 并行分发
    """
    if not state.get("questionIsClear", False):
        return "human_input"

    # Map 操作：将每个重写后的问题分发给 process_question 子图
    return [
        Send("process_question", {
            "question": q,
            "question_index": i,
            "messages": []
        })
        for i, q in enumerate(state.get("rewrittenQuestions", []))
    ]


# --- 构建图 ---
def create_graph():
    # 1. 准备组件
    llm = ModelFactory.get_llm()
    # 将 LlamaIndex 封装的 LangChain LLM 转换为 ChatModel 接口 (如果 factory 返回的是 BaseLLM)
    # 注意：LlamaIndex 的 DashScope 已经是 LLM，但在 LangGraph 中我们最好用 LangChain 的 ChatOpenAI 适配器
    # 或者直接使用 LangChain 的 ChatOpenAI 连接 DashScope (推荐方案，如下)

    # 【工程化修正】
    # 为了让 LangGraph 运行得更顺畅，控制层的 LLM 建议直接用 LangChain 原生组件
    # 只有数据层的 Embedding/LLM 才必须用 LlamaIndex 组件
    # 这里我们临时实例化一个 LangChain 的 ChatOpenAI 指向百炼，以获得最佳的 bind_tools 支持
    from langchain_openai import ChatOpenAI
    from app.settings import settings

    ctrl_llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.dashscope_api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0.1
    )

    tools = get_tools()
    llm_with_tools = ctrl_llm.bind_tools(tools)

    # 2. 构建子图 (Agent Subgraph)
    agent_builder = StateGraph(AgentState)
    agent_builder.add_node("agent", partial(agent_node, llm_with_tools=llm_with_tools))
    agent_builder.add_node("tools", ToolNode(tools))
    agent_builder.add_node("extract_answer", extract_final_answer)

    agent_builder.add_edge(START, "agent")
    agent_builder.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: "extract_answer"})
    agent_builder.add_edge("tools", "agent")
    agent_builder.add_edge("extract_answer", END)

    agent_subgraph = agent_builder.compile()

    # 3. 构建主图 (Main Graph)
    workflow = StateGraph(State)

    workflow.add_node("summarize", partial(analyze_chat_and_summarize, llm=ctrl_llm))
    workflow.add_node("analyze_rewrite", partial(analyze_and_rewrite_query, llm=ctrl_llm))
    workflow.add_node("human_input", human_input_node)
    workflow.add_node("process_question", agent_subgraph)
    workflow.add_node("aggregate", partial(aggregate_responses, llm=ctrl_llm))

    # 定义边
    workflow.add_edge(START, "summarize")
    workflow.add_edge("summarize", "analyze_rewrite")
    workflow.add_conditional_edges("analyze_rewrite", route_after_rewrite)
    workflow.add_edge("human_input", "analyze_rewrite")  # 循环：人工确认后重新分析
    workflow.add_edge("process_question", "aggregate")
    workflow.add_edge("aggregate", END)

    # 4. 编译
    checkpointer = InMemorySaver()
    return workflow.compile(checkpointer=checkpointer, interrupt_before=["human_input"])