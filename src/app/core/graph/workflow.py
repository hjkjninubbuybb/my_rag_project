from functools import partial
from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition
# 👇【LangGraph 0.2.x 适配】这里从 InMemorySaver 改名为 MemorySaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Send
from langchain_openai import ChatOpenAI

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
from app.settings import settings


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

    # 控制层 LLM：使用 LangChain 原生组件连接阿里云百炼
    # 这能获得对 Tool Calling 的最佳支持
    ctrl_llm = ChatOpenAI(
        model=settings.llm_model,
        # 👇【关键】参数名必须是 openai_api_key，否则 LangChain 可能会报权限错误
        openai_api_key=settings.dashscope_api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0.1
    )

    tools = get_tools()
    llm_with_tools = ctrl_llm.bind_tools(tools)

    # 2. 构建子图 (Agent Subgraph - ReAct 循环)
    agent_builder = StateGraph(AgentState)

    # 添加节点
    agent_builder.add_node("agent", partial(agent_node, llm_with_tools=llm_with_tools))
    agent_builder.add_node("tools", ToolNode(tools))  # 使用 LangGraph 预置的 ToolNode
    agent_builder.add_node("extract_answer", extract_final_answer)

    # 定义边
    agent_builder.add_edge(START, "agent")
    # tools_condition 会自动判断：如果 LLM 返回 tool_calls -> 去 "tools"；否则 -> 去 "extract_answer"
    agent_builder.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: "extract_answer"})
    agent_builder.add_edge("tools", "agent")  # 工具执行完，回 agent 继续思考
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
    # 👇【LangGraph 0.2.x 适配】使用 MemorySaver
    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer, interrupt_before=["human_input"])