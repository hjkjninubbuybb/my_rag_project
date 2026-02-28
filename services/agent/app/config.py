"""Agent 服务级配置。"""

from pydantic_settings import BaseSettings


class ServiceSettings(BaseSettings):
    """Agent 服务配置，从环境变量加载。"""

    # Indexing Service URL (用于调用检索 API)
    indexing_url: str = "http://localhost:8001"

    # 服务端口
    host: str = "0.0.0.0"
    port: int = 8002

    # DashScope
    dashscope_api_key: str = ""

    model_config = {"env_prefix": "", "env_file": ".env"}


service_settings = ServiceSettings()
