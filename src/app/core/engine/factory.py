from llama_index.llms.dashscope import DashScope
# 👇【关键修改 1】导入通用的 OpenAI Embedding 类
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.postprocessor.dashscope_rerank import DashScopeRerank

from app.settings import settings

class ModelFactory:
    @staticmethod
    def get_llm():
        """
        获取 LLM 模型 (Qwen)
        """
        return DashScope(
            model_name=settings.llm_model,
            api_key=settings.dashscope_api_key,
            temperature=0.1
        )

    @staticmethod
    def get_embedding():
        """
        获取 Embedding 模型
        👇【关键修改 2】使用 OpenAI 兼容模式调用 text-embedding-v4
        这完全对应你发的官方代码示例
        """
        return OpenAIEmbedding(
            model_name=settings.embedding_model, # text-embedding-v4
            api_key=settings.dashscope_api_key,
            # 👇 阿里云百炼的兼容接口地址
            api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            embed_batch_size=10,  # 批处理大小，防止请求过大
            # 维度自适应 (v4 默认可能是 1536 或 1024，显式指定更安全，这里由模型决定)
        )

    @staticmethod
    def get_rerank():
        """
        获取 Rerank 重排序模型
        """
        return DashScopeRerank(
            model="gte-rerank",
            api_key=settings.dashscope_api_key,
            top_n=5
        )