"""Agent Service API Schemas."""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


# ─── Chat Schemas ───────────────────────────────────────────────

class ChatRequest(BaseModel):
    """SSE 流式聊天请求。"""
    message: str = Field(..., description="用户消息")
    config: Dict[str, Any] = Field(default_factory=dict, description="实验配置")
    thread_id: Optional[str] = Field(None, description="对话线程 ID（用于多轮对话）")


class ChatResetRequest(BaseModel):
    """重置聊天状态请求。"""
    thread_id: str = Field(..., description="要重置的线程 ID")


# ─── VLM Schemas ───────────────────────────────────────────────

class VLMAnalyzeRequest(BaseModel):
    """VLM 图像分析请求（用于 Indexing Service 调用）。"""
    image_base64: str = Field(..., description="Base64 编码的图像")
    image_type: str = Field(default="screenshot", description="图像类型")
    surrounding_text: Optional[str] = Field(None, description="图像周围的上下文文本")
    prompt: Optional[str] = Field(None, description="自定义 prompt")


class VLMAnalyzeResponse(BaseModel):
    """VLM 图像分析响应。"""
    summary: str = Field(..., description="图像摘要文本")
    confidence: float = Field(default=1.0, description="置信度（保留字段）")


class VLMSummarizeRequest(BaseModel):
    """VLM 批量图像摘要请求。"""
    images: List[Dict[str, Any]] = Field(..., description="图像列表，每个包含 base64, type, surrounding_text")
    model_name: str = Field(default="qwen-vl-max", description="VLM 模型名称")


class VLMSummarizeResponse(BaseModel):
    """VLM 批量图像摘要响应。"""
    summaries: List[str] = Field(..., description="图像摘要列表")
    total: int = Field(..., description="处理的图像总数")
