"""Inference 服务级配置。"""

from pydantic_settings import BaseSettings


class ServiceSettings(BaseSettings):
    """Inference 服务配置，从环境变量加载。"""

    # Qdrant
    qdrant_url: str = "http://localhost:6333"

    # 服务端口
    host: str = "0.0.0.0"
    port: int = 8002

    # DashScope
    dashscope_api_key: str = ""

    model_config = {"env_prefix": "", "env_file": ".env"}


service_settings = ServiceSettings()
