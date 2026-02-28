"""DashScope LLM Provider (simplified version without ComponentRegistry)."""

from langchain_community.chat_models.tongyi import ChatTongyi

from app.utils.logger import get_logger

logger = get_logger(__name__)


def create_dashscope_llm(model_name: str, api_key: str, temperature: float = 0.1):
    """Create DashScope LLM instance.

    Args:
        model_name: Model name (e.g., "qwen-plus", "qwen-max")
        api_key: DashScope API key
        temperature: Temperature for generation

    Returns:
        ChatTongyi instance
    """
    llm = ChatTongyi(
        model=model_name,
        dashscope_api_key=api_key,
        temperature=temperature,
    )

    logger.info(f"DashScope LLM created: model={model_name}, temperature={temperature}")
    return llm
