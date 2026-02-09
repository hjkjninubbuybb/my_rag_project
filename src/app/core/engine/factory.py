"""
[Architecture Role: Model Factory (模型工厂)]
此模块负责生产 LLM 和 Embedding 模型实例。

关键架构决策 (Architectural Decision Record):
我们使用 `OpenAIEmbedding` 类来调用阿里云百炼 (DashScope) 的 text-embedding-v4 模型，
而不是使用原生的 `DashScopeEmbedding` 类。

原因:
1. LlamaIndex 原生 SDK 对 DashScope v4 的支持可能存在版本滞后或参数不兼容。
2. 阿里云提供了完美的 OpenAI 兼容接口 (/compatible-mode/v1)。
3. 这种方式更稳定，且支持 batch_size 控制，防止 API 超时。
"""

from llama_index.llms.dashscope import DashScope
# 👇【关键依赖】使用通用的 OpenAI 类，而非阿里专用类
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.postprocessor.dashscope_rerank import DashScopeRerank

from app.settings import settings


class ModelFactory:
    @staticmethod
    def get_llm():
        """
        获取 LLM 模型 (Qwen-plus/max)
        """
        return DashScope(
            model_name=settings.llm_model,
            api_key=settings.dashscope_api_key,
            temperature=0.1
        )

    @staticmethod
    def get_embedding():
        """
        [Critical Configuration] 获取 Embedding 模型

        注意：这里利用了阿里云的 OpenAI 兼容接口。
        - model_name: text-embedding-v4
        - api_base: https://dashscope.aliyuncs.com/compatible-mode/v1
        """
        return OpenAIEmbedding(
            model_name=settings.embedding_model,  # text-embedding-v4
            api_key=settings.dashscope_api_key,
            # 👇 核心：指向阿里云的兼容端点
            api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            embed_batch_size=10,  # 批处理大小，防止请求过大导致超时
            # 维度自适应 (v4 默认可能是 1536 或 1024，显式指定更安全，这里由模型决定)
        )

    @staticmethod
    def get_rerank():
        """
        获取 Rerank 重排序模型 (GTE-Rerank)
        """
        return DashScopeRerank(
            model="gte-rerank",
            api_key=settings.dashscope_api_key,
            top_n=5
        )