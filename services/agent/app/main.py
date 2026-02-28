"""Agent Service — FastAPI 入口。"""

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
    print(f"[Agent] Service ready on {service_settings.host}:{service_settings.port}")
    print(f"[Agent] Indexing Service: {service_settings.indexing_url}")
    yield
    print("[Agent] Shutting down...")


app_instance = FastAPI(
    title="RAG Agent Service",
    description="Pure LLM/VLM Service — LangGraph Agent workflow, VLM analysis, no direct DB access",
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
