"""DashScope Embedding 供应商（Ingestion 服务仅需 Embedding）。"""

from llama_index.embeddings.openai import OpenAIEmbedding

from rag_shared.core.registry import ComponentRegistry
from rag_shared.core.types import BaseEmbeddingProvider


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
