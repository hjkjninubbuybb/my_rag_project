"""Agent Service API 路由。"""

import json
import uuid
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.schemas import (
    ChatRequest,
    ChatResetRequest,
    VLMAnalyzeRequest,
    VLMAnalyzeResponse,
    VLMSummarizeRequest,
    VLMSummarizeResponse,
)
from app.config import service_settings
from app.agent.workflow import create_graph
from app.services.vlm import VLMService
from app.utils.logger import get_logger

from langchain_core.messages import HumanMessage

router = APIRouter()
logger = get_logger(__name__)

# --- 图实例缓存 (config fingerprint → graph) ---
_graph_cache: Dict[str, Any] = {}


def _get_or_create_graph(config: dict):
    """按配置指纹缓存 LangGraph 实例。"""
    llm_model = config.get("llm_model", "qwen-plus")
    collection_name = config.get("collection_name", "default")
    key = f"{llm_model}_{collection_name}"

    if key not in _graph_cache:
        _graph_cache[key] = create_graph(config)
        logger.info(f"创建新的 LangGraph 实例: {key}")

    return _graph_cache[key]


def _build_config(config_dict: Dict[str, Any]) -> Dict[str, Any]:
    """从 API 请求构建配置，注入服务级默认值。"""
    if not config_dict.get("dashscope_api_key"):
        config_dict["dashscope_api_key"] = service_settings.dashscope_api_key
    return config_dict


# ─── 聊天流式 API ─────────────────────────────────────────────

@router.post("/chat")
async def chat_stream(request: ChatRequest):
    """SSE 流式聊天接口。

    通过 LangGraph Agent 工作流处理用户消息，流式返回响应。
    """
    try:
        config = _build_config(request.config)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid config: {e}")

    graph = _get_or_create_graph(config)
    thread_id = request.thread_id or str(uuid.uuid4())

    lc_config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 25,
    }

    inputs = {"messages": [HumanMessage(content=request.message)]}

    async def event_generator():
        try:
            final_state = None
            async for event in graph.astream_events(inputs, config=lc_config, version="v2"):
                kind = event.get("event", "")
                name = event.get("name", "")

                # Token 流式输出
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        # 只输出 aggregate 节点的 token (最终回答)
                        tags = event.get("tags", [])
                        if "aggregate" in tags or not tags:
                            yield {
                                "event": "token",
                                "data": json.dumps(
                                    {"content": chunk.content},
                                    ensure_ascii=False,
                                ),
                            }

                # Query Rewrite 事件
                elif kind == "on_chain_end" and name == "analyze_rewrite":
                    output = event.get("data", {}).get("output", {})
                    questions = output.get("rewrittenQuestions", [])
                    if questions:
                        yield {
                            "event": "rewrite",
                            "data": json.dumps(
                                {"questions": questions},
                                ensure_ascii=False,
                            ),
                        }

                # 记录最终 state
                elif kind == "on_chain_end" and name == "LangGraph":
                    final_state = event.get("data", {}).get("output", {})

            # 发送 debug chunks
            if final_state:
                chunks = final_state.get("debug_retrieved_chunks", [])
                if chunks:
                    yield {
                        "event": "chunks",
                        "data": json.dumps(chunks, ensure_ascii=False),
                    }

            yield {"event": "done", "data": json.dumps({"status": "ok"})}

        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            yield {
                "event": "error",
                "data": json.dumps(
                    {"error": str(e)},
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(event_generator())


@router.post("/chat/reset")
async def chat_reset(request: ChatResetRequest):
    """重置聊天状态（清除 checkpointer 中的 thread）。

    注意：MemorySaver 不支持删除，客户端应使用新的 thread_id 创建新对话。
    """
    return {
        "status": "ok",
        "message": "MemorySaver 不支持删除，请使用新的 thread_id 创建新对话",
        "thread_id": request.thread_id,
    }


# ─── VLM API ─────────────────────────────────────────────────

@router.post("/vlm/analyze", response_model=VLMAnalyzeResponse)
async def vlm_analyze(request: VLMAnalyzeRequest):
    """VLM 图像分析接口（供 Indexing Service 调用）。

    接收 base64 编码的图像，返回 VLM 生成的摘要文本。
    """
    try:
        vlm_service = VLMService(
            api_key=service_settings.dashscope_api_key,
            model_name="qwen-vl-max"
        )

        summary = vlm_service.analyze_image(
            image_base64=request.image_base64,
            image_type=request.image_type,
            surrounding_text=request.surrounding_text,
            prompt=request.prompt,
        )

        return VLMAnalyzeResponse(summary=summary, confidence=1.0)

    except Exception as e:
        logger.error(f"VLM analyze error: {e}")
        raise HTTPException(status_code=500, detail=f"VLM analysis failed: {str(e)}")


@router.post("/vlm/summarize", response_model=VLMSummarizeResponse)
async def vlm_summarize(request: VLMSummarizeRequest):
    """VLM 批量图像摘要接口。

    接收多张图像，批量生成摘要。
    """
    try:
        vlm_service = VLMService(
            api_key=service_settings.dashscope_api_key,
            model_name=request.model_name
        )

        summaries = vlm_service.batch_summarize(images=request.images)

        return VLMSummarizeResponse(summaries=summaries, total=len(summaries))

    except Exception as e:
        logger.error(f"VLM batch summarize error: {e}")
        raise HTTPException(status_code=500, detail=f"VLM batch summarization failed: {str(e)}")


# ─── 健康检查 ─────────────────────────────────────────────────

@router.get("/health")
async def health_check():
    """健康检查端点。"""
    return {
        "status": "healthy",
        "service": "agent",
        "indexing_url": service_settings.indexing_url,
    }
