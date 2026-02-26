"""Inference Service — FastAPI 入口。"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import service_settings


# 环境预设
os.environ.setdefault("no_proxy", "localhost,127.0.0.1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """服务生命周期管理。"""
    # 启动: 预热 jieba (用于 sparse 向量)
    from app.components.providers.bgem3 import SparseModelManager
    SparseModelManager.warmup()
    print(f"[Inference] Service ready on {service_settings.host}:{service_settings.port}")
    print(f"[Inference] Qdrant: {service_settings.qdrant_url}")
    yield
    # 关闭: 清理资源
    print("[Inference] Shutting down...")


# 触发组件自注册
import app  # noqa: F401, E402

app_instance = FastAPI(
    title="RAG Inference Service",
    description="核心问答与 Agent 工作流服务 — LangGraph Agent、检索、SSE 流式输出",
    version="0.1.0",
    lifespan=lifespan,
)

# 注册路由
from app.api.routes import router  # noqa: E402
app_instance.include_router(router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app_instance",
        host=service_settings.host,
        port=service_settings.port,
        reload=True,
    )
