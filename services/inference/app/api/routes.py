"""Inference Service API 路由。"""

import json
import uuid
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from rag_shared.config.experiment import ExperimentConfig
from rag_shared.core.registry import ComponentRegistry
from rag_shared.schemas.inference import (
    ChatRequest,
    ChatResetRequest,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
    RetrievalNode,
    EvaluateRequest,
    EvaluateResponse,
)
from app.config import service_settings
from app.agent.workflow import create_graph
from app.services.retrieval import RetrievalService

from langchain_core.messages import HumanMessage

router = APIRouter()

# --- 图实例缓存 (config fingerprint → graph) ---
_graph_cache: Dict[str, Any] = {}


def _get_or_create_graph(config: ExperimentConfig):
    """按配置指纹缓存 LangGraph 实例。"""
    key = f"{config.llm_provider}_{config.llm_model}_{config.collection_name}"
    if key not in _graph_cache:
        _graph_cache[key] = create_graph(config)
    return _graph_cache[key]


def _build_config(config_dict: Dict[str, Any]) -> ExperimentConfig:
    """从 API 请求构建 ExperimentConfig，注入服务级默认值。"""
    if not config_dict.get("dashscope_api_key"):
        config_dict["dashscope_api_key"] = service_settings.dashscope_api_key
    if not config_dict.get("qdrant_url"):
        config_dict["qdrant_url"] = service_settings.qdrant_url
    return ExperimentConfig.from_dict(config_dict)


# ─── 聊天流式 API ─────────────────────────────────────────────

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE 流式聊天接口。"""
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
    """重置聊天状态（清除 checkpointer 中的 thread）。"""
    # MemorySaver 不支持删除，返回成功即可（客户端用新 thread_id）
    return {"status": "ok", "message": f"Thread '{request.thread_id}' reset. Use a new thread_id."}


# ─── 直接检索 API ─────────────────────────────────────────────

@router.post("/retrieval/search", response_model=RetrievalSearchResponse)
async def retrieval_search(request: RetrievalSearchRequest):
    """直接检索（不经过 Agent）。"""
    try:
        config = _build_config(request.config)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid config: {e}")

    service = RetrievalService(config)
    retriever = service.get_retriever()
    nodes = retriever.retrieve(request.query)

    result_nodes = []
    for node_with_score in nodes[:request.top_k]:
        result_nodes.append(RetrievalNode(
            text=node_with_score.node.text[:500],
            score=round(float(node_with_score.score or 0), 4),
            source_file=node_with_score.node.metadata.get("file_name", "unknown"),
        ))

    return RetrievalSearchResponse(nodes=result_nodes)


# ─── 评测 API ─────────────────────────────────────────────────

@router.post("/evaluate/single", response_model=EvaluateResponse)
async def evaluate_single(request: EvaluateRequest):
    """单配置评测：对数据集执行检索并计算指标。"""
    try:
        config = _build_config(request.config)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid config: {e}")

    service = RetrievalService(config)
    retriever = service.get_retriever()

    dataset = request.dataset
    if request.limit:
        dataset = dataset[:request.limit]

    details = []
    total_hit = 0
    total_mrr = 0.0

    for row in dataset:
        nodes = retriever.retrieve(row.query)
        top_texts = [n.node.text for n in nodes]

        # 简单的命中判断: ground_truth 是否为某个检索结果的子串
        hit = False
        rank = 0
        for i, text in enumerate(top_texts):
            if row.ground_truth in text or text in row.ground_truth:
                hit = True
                rank = i + 1
                break

        total_hit += int(hit)
        total_mrr += (1.0 / rank) if rank > 0 else 0.0

        details.append({
            "query": row.query,
            "ground_truth": row.ground_truth,
            "category": row.category,
            "hit": hit,
            "rank": rank,
            "top_k_count": len(top_texts),
        })

    n = len(dataset) if dataset else 1
    summary = {
        "total": len(dataset),
        "hit_rate": round(total_hit / n, 4),
        "mrr": round(total_mrr / n, 4),
        "collection_name": config.collection_name,
        "config_id": config.experiment_id,
    }

    return EvaluateResponse(summary=summary, details=details)


# ─── 多模态聊天 API ────────────────────────────────────────────

@router.post("/multimodal/chat")
async def multimodal_chat(request: Dict[str, Any]):
    """多模态聊天端点（截图 + 文本 → 操作指导）。

    与纯文本端点 /chat/stream 并行，由分类 agent 路由。

    Request Body:
    {
        "message": str,  # 用户文字描述
        "images": [str],  # base64 编码的图片列表（用户截图）
        "config": dict,  # ExperimentConfig 字典
        "thread_id": str  # 可选
    }

    Response:
    {
        "answer": str,  # AI 生成的操作指导
        "reference_images": [  # 参考截图（来自手册）
            {
                "page": int,
                "file": str,
                "base64": str
            }
        ],
        "debug_info": dict  # 调试信息
    }
    """
    from rag_shared.schemas.multimodal import MultimodalChatRequest
    from app.services.multimodal_retrieval import MultimodalRetrievalService
    from app.components.providers.qwen_vl_llm import QwenVLLLMProvider

    # 1. 解析请求
    try:
        mm_request = MultimodalChatRequest(**request)
        config = _build_config(mm_request.config)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}")

    # 验证多模态配置
    if not config.enable_multimodal:
        raise HTTPException(
            status_code=400,
            detail="Multimodal not enabled in config. Set enable_multimodal=true.",
        )

    if not mm_request.images:
        raise HTTPException(
            status_code=400,
            detail="No images provided. Use /chat/stream for text-only queries.",
        )

    # 2. 检索相关图文对（使用图像向量）
    retrieval_service = MultimodalRetrievalService(config)

    import base64
    image_bytes = base64.b64decode(mm_request.images[0])

    # 使用用户角色过滤（如果配置中有）
    user_role = config.user_role

    search_results = retrieval_service.search_by_image(
        image_bytes, top_k=3, user_role=user_role
    )

    # 3. 构建多模态 prompt
    llm_provider_class = ComponentRegistry.get_multimodal_llm_provider("qwen-vl")
    llm_provider = llm_provider_class()

    llm = llm_provider.create_multimodal_llm(
        model_name=config.multimodal_llm_model,
        api_key=config.dashscope_api_key,
        temperature=config.llm_temperature,
    )

    # 构建上下文
    context_text = "\n\n".join(
        [
            f"参考步骤 {i+1} (来自 {r['source_file']} 第{r['page']}页):\n{r['text']}"
            for i, r in enumerate(search_results)
        ]
    )

    # 提取参考截图
    context_images = []
    reference_images = []
    for r in search_results:
        if "images" in r["metadata"] and r["metadata"]["images"]:
            img_data = r["metadata"]["images"][0]  # 取第一张图片
            context_images.append(img_data["base64"])
            reference_images.append({
                "page": r["page"],
                "file": r["source_file"],
                "base64": img_data["base64"],
            })

    # 构建 prompt
    prompt = f"""用户上传了系统截图，请识别当前状态并提供操作指导。

参考手册内容：
{context_text}

请对比用户截图和参考手册，说明：
1. 用户当前所处的操作步骤
2. 接下来应该如何操作（具体点击哪里）
3. 可能遇到的问题和解决方案
"""

    # 构建多模态消息（用户截图 + 参考截图）
    all_images = [mm_request.images[0]] + context_images[:2]  # 用户截图 + 最多2张参考截图

    message = QwenVLLLMProvider.create_multimodal_message(
        text=prompt,
        images=all_images,
    )

    # 4. 生成回答
    try:
        response = llm.invoke([message])
        answer = response.content

        return {
            "answer": answer,
            "reference_images": reference_images,
            "debug_info": {
                "retrieval_count": len(search_results),
                "context_images_count": len(context_images),
                "user_role": user_role,
                "collection_name": config.collection_name,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM generation failed: {e}")
