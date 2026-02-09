from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import AutoMergingRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.tools import QueryEngineTool, ToolMetadata

from app.core.engine.store import VectorStoreManager
from app.core.engine.factory import ModelFactory


class RetrievalService:
    def __init__(self):
        self.store_manager = VectorStoreManager()
        self.llm = ModelFactory.get_llm()
        self.embed_model = ModelFactory.get_embedding()

    def get_query_engine(self):
        """
        构建带有自动合并功能的查询引擎
        """
        # 1. 重新加载 Index
        storage_context = self.store_manager.get_storage_context()

        index = VectorStoreIndex.from_vector_store(
            vector_store=storage_context.vector_store,
            storage_context=storage_context,
            embed_model=self.embed_model
        )

        # 2. 基础检索器 (查 Top-10 子块)
        base_retriever = index.as_retriever(similarity_top_k=10)

        # 3. 自动合并检索器 (核心逻辑)
        # 如果某个父块下的子块被查到多次，就自动替换为父块
        retriever = AutoMergingRetriever(
            vector_retriever=base_retriever,
            storage_context=storage_context,
            verbose=True
        )

        # 4. 构建引擎 (Retriever + LLM)
        query_engine = RetrieverQueryEngine.from_args(
            retriever=retriever,
            llm=self.llm
        )

        return query_engine

    def as_langchain_tool(self):
        """
        转换为 LangChain Tool，供 LangGraph 使用
        """
        query_engine = self.get_query_engine()

        # LlamaIndex 提供的适配器
        tool = QueryEngineTool(
            query_engine=query_engine,
            metadata=ToolMetadata(
                name="knowledge_base_search",
                description="用于检索内部文档知识库。输入完整的问题进行查询。",
            ),
        )

        # 转换为 LangChain 兼容格式
        return tool.to_langchain_tool()