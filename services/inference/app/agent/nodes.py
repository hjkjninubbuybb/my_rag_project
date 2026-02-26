"""
LangGraph 图节点实现。

节点职责：
1. summarize    — 压缩对话历史
2. rewrite      — LLM 驱动的问题分析与拆分
3. agent        — ReAct 循环（工具调用）
4. extract      — 提取最终答案 + 收集 debug 数据
5. aggregate    — 聚合多子问题答案（单问题直通）
"""

import json
import base64

from langchain_core.messages import (
    SystemMessage, HumanMessage, AIMessage, ToolMessage,
)
from langchain_core.language_models import BaseChatModel

from app.agent.state import State, AgentState
from app.agent.prompts import (
    get_conversation_summary_prompt,
    get_query_rewrite_prompt,
    get_rag_agent_prompt,
    get_aggregation_prompt,
)
from rag_shared.core.registry import ComponentRegistry


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

    summary_llm = llm.with_config(temperature=0.1)
    response = await summary_llm.ainvoke(
        [SystemMessage(content=get_conversation_summary_prompt())] +
        [HumanMessage(content=conversation)]
    )

    return {
        "conversation_summary": response.content,
        "agent_answers": [{"__reset__": True}],
        "debug_retrieved_chunks": [],
    }


# --- 节点 2: 问题分析与拆分 ---
async def analyze_and_rewrite_query(state: State, llm: BaseChatModel):
    """
    LLM 驱动的问题分析：判断是否需要拆分为多个子问题。
    解析失败时降级为直通模式，保证健壮性。
    """
    last_message = state["messages"][-1]
    query = last_message.content
    summary = state.get("conversation_summary", "")

    # 构造带上下文的输入
    user_input = query
    if summary:
        user_input = f"对话背景: {summary}\n当前问题: {query}"

    try:
        response = await llm.ainvoke([
            SystemMessage(content=get_query_rewrite_prompt()),
            HumanMessage(content=user_input),
        ])

        result = json.loads(response.content)
        questions = result.get("questions", [query])
        if not questions:
            questions = [query]
    except (json.JSONDecodeError, KeyError, Exception):
        # 降级为直通
        questions = [query]

    return {
        "questionIsClear": True,
        "originalQuery": query,
        "rewrittenQuestions": questions,
    }


# --- 节点 3: 执行 Agent (ReAct) ---
async def agent_node(state: AgentState, llm_with_tools: BaseChatModel, config=None):
    """Agent 节点：支持多模态 VLM 生成。

    检测 ToolMessage 中的图片数据，如果存在则使用 VLM 生成答案。
    """
    sys_msg = SystemMessage(content=get_rag_agent_prompt())

    # 第一次进入子图：messages 为空，将 question 作为 HumanMessage
    if not state.get("messages"):
        human_msg = HumanMessage(content=state["question"])
        response = await llm_with_tools.ainvoke([sys_msg, human_msg])
        return {"messages": [human_msg, response]}

    # 检测是否有多模态数据（图片）
    has_images = False
    image_data_list = []
    text_context = ""

    for msg in state["messages"]:
        if isinstance(msg, ToolMessage) and getattr(msg, "artifact", None):
            for chunk in msg.artifact:
                if chunk.get("is_multimodal") and chunk.get("image_data"):
                    has_images = True
                    image_data_list.append(chunk["image_data"])
                    text_context += chunk.get("text", "") + "\n"

    # 如果检测到图片，使用 VLM 生成
    if has_images and config and config.enable_multimodal:
        try:
            # 获取 VLM Provider
            vlm_provider_class = ComponentRegistry.get_vlm_provider("dashscope")
            vlm_provider = vlm_provider_class(
                api_key=config.dashscope_api_key,
                model_name=config.multimodal_llm_model
            )

            # 提取图片 base64 数据
            images_bytes = []
            for img_data in image_data_list:
                img_base64 = img_data.get("base64", "")
                if img_base64:
                    images_bytes.append(base64.b64decode(img_base64))

            # 使用 VLM 生成答案
            if images_bytes:
                answer = vlm_provider.generate_with_images(
                    query=state["question"],
                    text_context=text_context,
                    images=images_bytes,
                    temperature=0.7
                )

                # 返回 VLM 生成的答案
                ai_msg = AIMessage(content=answer)
                return {"messages": [ai_msg]}

        except Exception as e:
            print(f"[Warning] VLM 生成失败，降级为普通 LLM: {e}")
            # 降级：继续使用普通 LLM

    # 后续轮次（Tool 执行完回来），带上历史继续推理
    response = await llm_with_tools.ainvoke([sys_msg] + state["messages"])
    return {"messages": [response]}


# --- 节点 4: 提取最终答案 ---
def extract_final_answer(state: AgentState):
    # 收集所有 ToolMessage 的 artifact（检索 debug 数据）
    debug_chunks = []
    for msg in state["messages"]:
        if isinstance(msg, ToolMessage) and getattr(msg, "artifact", None):
            debug_chunks.extend(msg.artifact)

    # 倒序查找最后一条 AI 的文本回复（且没有工具调用）
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
            return {
                "final_answer": msg.content,
                "agent_answers": [{
                    "index": state["question_index"],
                    "question": state["question"],
                    "answer": msg.content,
                }],
                "debug_retrieved_chunks": debug_chunks,
            }

    return {
        "final_answer": "No answer found.",
        "agent_answers": [{
            "index": state["question_index"],
            "question": state["question"],
            "answer": "抱歉，未能找到相关答案。",
        }],
        "debug_retrieved_chunks": debug_chunks,
    }


# --- 节点 5: 聚合回答 ---
async def aggregate_responses(state: State, llm: BaseChatModel):
    answers = state.get("agent_answers", [])
    if not answers:
        return {"messages": [AIMessage(content="未生成任何回答。")]}

    sorted_answers = sorted(answers, key=lambda x: x["index"])

    # 单问题直通：跳过 LLM 聚合调用，减少延迟
    if len(sorted_answers) == 1:
        return {"messages": [AIMessage(content=sorted_answers[0]["answer"])]}

    # 多问题：LLM 聚合
    formatted = "\n".join([
        f"子问题 {i + 1}: {ans['question']}\n回答:\n{ans['answer']}\n"
        for i, ans in enumerate(sorted_answers)
    ])

    user_msg = HumanMessage(
        content=f"原始问题: {state['originalQuery']}\n\n检索到的分答案:\n{formatted}"
    )

    response = await llm.ainvoke(
        [SystemMessage(content=get_aggregation_prompt()), user_msg]
    )

    return {"messages": [response]}
