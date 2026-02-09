from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, RemoveMessage
from langchain_core.language_models import BaseChatModel

from app.core.graph.state import State, AgentState
from app.core.graph.prompts import (
    get_conversation_summary_prompt,
    get_rag_agent_prompt,
    get_aggregation_prompt
)


# --- 节点 1: 总结对话 ---
async def analyze_chat_and_summarize(state: State, llm: BaseChatModel):
    messages = state.get("messages", [])
    if len(messages) < 4:
        return {"conversation_summary": ""}

    # 过滤掉 ToolMessage，只保留人机对话
    relevant_msgs = [
        msg for msg in messages[:-1]
        if isinstance(msg, (HumanMessage, AIMessage))
           and not getattr(msg, "tool_calls", None)
    ]

    if not relevant_msgs:
        return {"conversation_summary": ""}

    conversation = "Conversation history:\n"
    for msg in relevant_msgs[-6:]:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        conversation += f"{role}: {msg.content}\n"

    # 使用较低温度进行总结
    summary_llm = llm.with_config(temperature=0.1)
    response = await summary_llm.ainvoke(
        [SystemMessage(content=get_conversation_summary_prompt())] +
        [HumanMessage(content=conversation)]
    )

    # 返回总结，并重置 agent_answers（准备开始新一轮搜索）
    return {
        "conversation_summary": response.content,
        "agent_answers": [{"__reset__": True}]
    }


# --- 节点 2: 问题分析与重写 (直通优化版) ---
async def analyze_and_rewrite_query(state: State, llm: BaseChatModel):
    """
    直通模式：直接将用户问题作为搜索查询
    如果需要改写，可以在这里接入 LLM，但目前保持直通以确保稳定性。
    """
    last_message = state["messages"][-1]
    query = last_message.content

    # 简单逻辑：默认问题是清晰的
    # 如果需要复杂的意图识别，可以在这里扩展
    return {
        "questionIsClear": True,
        "originalQuery": query,
        "rewrittenQuestions": [query]  # 保持列表格式，兼容后续的 Map 操作
    }


# --- 节点 3: 人工介入 (占位符) ---
def human_input_node(state: State):
    # LangGraph 会在这里中断 (interrupt_before)
    return {}


# --- 节点 4: 执行 Agent (ReAct) ---
async def agent_node(state: AgentState, llm_with_tools: BaseChatModel):
    sys_msg = SystemMessage(content=get_rag_agent_prompt())

    # 如果是第一次进入子图，messages 为空，需要把 question 塞进去
    if not state.get("messages"):
        human_msg = HumanMessage(content=state["question"])
        response = await llm_with_tools.ainvoke([sys_msg, human_msg])
        return {"messages": [human_msg, response]}

    # 后续轮次（Tool执行完回来），带上历史记录继续思考
    response = await llm_with_tools.ainvoke([sys_msg] + state["messages"])
    return {"messages": [response]}


# --- 节点 5: 提取最终答案 ---
def extract_final_answer(state: AgentState):
    # 倒序查找最后一条 AI 的文本回复（且没有工具调用）
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
            return {
                "final_answer": msg.content,
                "agent_answers": [{
                    "index": state["question_index"],
                    "question": state["question"],
                    "answer": msg.content
                }]
            }

    return {
        "final_answer": "No answer found.",
        "agent_answers": [{
            "index": state["question_index"],
            "question": state["question"],
            "answer": "抱歉，未能找到相关答案。"
        }]
    }


# --- 节点 6: 聚合回答 ---
async def aggregate_responses(state: State, llm: BaseChatModel):
    answers = state.get("agent_answers", [])
    if not answers:
        return {"messages": [AIMessage(content="未生成任何回答。")]}

    # 按索引排序，保证顺序一致
    sorted_answers = sorted(answers, key=lambda x: x["index"])

    formatted = "\n".join([
        f"Answer {i + 1}:\n{ans['answer']}\n"
        for i, ans in enumerate(sorted_answers)
    ])

    user_msg = HumanMessage(
        content=f"Original Question: {state['originalQuery']}\nRetrieved Answers:\n{formatted}"
    )

    response = await llm.ainvoke(
        [SystemMessage(content=get_aggregation_prompt()), user_msg]
    )

    return {"messages": [response]}