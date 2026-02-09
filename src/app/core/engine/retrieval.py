from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import AutoMergingRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.tools import QueryEngineTool, ToolMetadata

from app.core.engine.store import VectorStoreManager
from app.core.engine.factory import ModelFactory
# 👇【新增】导入 settings
from app.settings import settings


class RetrievalService:
    def __init__(self):
        self.store_manager = VectorStoreManager()
        self.llm = ModelFactory.get_llm()
        self.embed_model = ModelFactory.get_embedding()
        # 👇【新增】初始化 Reranker
        self.reranker = ModelFactory.get_rerank()

    def get_query_engine(self):
        """
        构建带有 [自动合并] + [混合检索] + [重排序] 功能的查询引擎
        """
        # 1. 重新加载 Index
        storage_context = self.store_manager.get_storage_context()

        index = VectorStoreIndex.from_vector_store(
            vector_store=storage_context.vector_store,
            storage_context=storage_context,
            embed_model=self.embed_model
        )

        # 2. 基础检索器 (Leaf Node Level)
        # 👇【关键修改】配置混合检索 + 扩大召回
        base_retriever = index.as_retriever(
            similarity_top_k=settings.retrieval_top_k, # 初筛 Top-50
            vector_store_query_mode="hybrid",          # 开启混合检索模式 (向量+关键词)
            alpha=0.5                                  # 语义与关键词权重平衡 (0.5=各占一半)
        )

        # 3. 自动合并检索器 (Auto-Merging)
        # 如果子块命中足够多，自动替换为父块
        retriever = AutoMergingRetriever(
            vector_retriever=base_retriever,
            storage_context=storage_context,
            verbose=True
        )

        # 4. 构建引擎 (Retriever + LLM)
        # 👇【关键修改】加入 Reranker 作为后置处理器
        query_engine = RetrieverQueryEngine.from_args(
            retriever=retriever,
            llm=self.llm,
            node_postprocessors=[self.reranker]        # 重排序：从 50 个精选为 10 个
        )

        return query_engine

    def as_langchain_tool(self):
        """
        转换为 LangChain Tool，供 LangGraph 使用
        """
        query_engine = self.get_query_engine()

        tool = QueryEngineTool(
            query_engine=query_engine,
            metadata=ToolMetadata(
                name="knowledge_base_search",
                description="用于检索内部文档知识库。输入完整的问题进行查询。",
            ),
        )

        return tool.to_langchain_tool()