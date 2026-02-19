from llama_index.llms.dashscope import DashScope
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.postprocessor.dashscope_rerank import DashScopeRerank

from rag.core.registry import ComponentRegistry
from rag.core.types import BaseLLMProvider, BaseEmbeddingProvider, BaseRerankerProvider


@ComponentRegistry.llm_provider("dashscope")
class DashScopeLLMProvider(BaseLLMProvider):
    """阿里云 DashScope LLM 供应商。"""

    _BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def create_llm(self, model_name: str, api_key: str, temperature: float, **kwargs):
        return DashScope(
            model_name=model_name,
            api_key=api_key,
            temperature=temperature,
        )

    def create_chat_model(self, model_name: str, api_key: str, temperature: float, **kwargs):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_name,
            openai_api_key=api_key,
            base_url=self._BASE_URL,
            temperature=temperature,
            **kwargs,
        )


@ComponentRegistry.embedding_provider("dashscope")
class DashScopeEmbeddingProvider(BaseEmbeddingProvider):
    """阿里云 DashScope Embedding 供应商 (通过 OpenAI 兼容接口)。"""

    def create_embedding(self, model_name: str, api_key: str, **kwargs):
        return OpenAIEmbedding(
            model_name=model_name,
            api_key=api_key,
            api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            embed_batch_size=10,
        )


@ComponentRegistry.reranker_provider("dashscope")
class DashScopeRerankerProvider(BaseRerankerProvider):
    """阿里云 DashScope Reranker 供应商。"""

    def create_reranker(self, model_name: str, api_key: str, top_n: int, **kwargs):
        return DashScopeRerank(
            model=model_name,
            api_key=api_key,
            top_n=top_n,
        )
