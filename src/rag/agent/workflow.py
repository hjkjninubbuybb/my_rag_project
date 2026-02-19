"""
LangGraph Agent 工作流。

接收 ExperimentConfig 进行依赖注入，通过 ComponentRegistry 创建 LLM。

图结构:
  START → summarize → analyze_rewrite → route → [process_question x N] → aggregate → END
"""

from functools import partial

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Send

from rag.config.experiment import ExperimentConfig
from rag.core.registry import ComponentRegistry
from rag.agent.state import State, AgentState
from rag.agent.tools import get_tools
from rag.agent.nodes import (
    analyze_chat_and_summarize,
    analyze_and_rewrite_query,
    agent_node,
    extract_final_answer,
    aggregate_responses,
)


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
def create_graph(config: ExperimentConfig):
    """根据实验配置构建 LangGraph Agent 工作流。"""

    # 通过注册中心获取 LLM Provider，创建 LangChain ChatModel
    provider = ComponentRegistry.get_llm_provider(config.llm_provider)
    ctrl_llm = provider.create_chat_model(
        model_name=config.llm_model,
        api_key=config.dashscope_api_key,
        temperature=config.llm_temperature,
    )

    tools = get_tools(config)
    llm_with_tools = ctrl_llm.bind_tools(tools)

    # 子图 (Agent Subgraph - ReAct 循环)
    agent_builder = StateGraph(AgentState)
    agent_builder.add_node("agent", partial(agent_node, llm_with_tools=llm_with_tools))
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
