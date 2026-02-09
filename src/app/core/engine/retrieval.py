"""
[Architecture Role: Retrieval Engine (检索引擎)]
此模块实现了 "三权分立" 架构中的 【检索层】。

核心职责:
1. [Advanced Retrieval] 构建复杂的检索流水线：
   - Hybrid Search (混合检索): 结合 向量相似度(语义) + 关键词匹配(字面)。
   - Auto-Merging (自动合并): 命中多个子块时，自动回溯父块以提供完整上下文。
   - Reranking (重排序): 使用 BGE/GTE 模型对召回结果进行二次精排。
2. [Bridge] 将 LlamaIndex 的查询引擎封装为 LangChain Tool，供 LangGraph Agent 调用。
"""

from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import AutoMergingRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.tools import QueryEngineTool, ToolMetadata

from app.core.engine.store import VectorStoreManager
from app.core.engine.factory import ModelFactory
from app.settings import settings


class RetrievalService:
    def __init__(self):
        self.store_manager = VectorStoreManager()
        self.llm = ModelFactory.get_llm()
        self.embed_model = ModelFactory.get_embedding()
        self.reranker = ModelFactory.get_rerank()

    def get_retriever(self, enable_hybrid: bool = True, enable_merge: bool = True):
        """
        [评测专用接口] 获取可配置的检索器

        Args:
            enable_hybrid (bool): 是否开启混合检索。
                                  True = 向量+关键词 (Hybrid, alpha=0.5)
                                  False = 纯向量 (Default)
            enable_merge (bool):  是否开启自动合并检索 (Auto-Merging)。
                                  True = 返回父文档
                                  False = 返回原始切片
        """
        # 1. 获取上下文
        storage_context = self.store_manager.get_storage_context()
        index = VectorStoreIndex.from_vector_store(
            vector_store=storage_context.vector_store,
            storage_context=storage_context,
            embed_model=self.embed_model
        )

        # 2. 配置基础检索模式 (Baseline vs Hybrid)
        # 如果 enable_hybrid 为 False，则使用 "default" 模式 (即纯向量检索)
        vector_mode = "hybrid" if enable_hybrid else "default"
        alpha_value = 0.5 if enable_hybrid else None

        base_retriever = index.as_retriever(
            similarity_top_k=settings.retrieval_top_k,  # 初筛数量 (例如 50)
            vector_store_query_mode=vector_mode,
            alpha=alpha_value
        )

        # 3. 配置结构化检索 (Auto-Merging)
        if enable_merge:
            return AutoMergingRetriever(
                vector_retriever=base_retriever,
                storage_context=storage_context,
                verbose=False  # 评测时关闭日志，保持清爽
            )
        else:
            return base_retriever

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
        base_retriever = index.as_retriever(
            similarity_top_k=settings.retrieval_top_k,
            # 👇【修复】改回字符串模式，并添加 type: ignore 让 IDE 闭嘴
            # 这样既不会报错，也没有黄色波浪线
            vector_store_query_mode="hybrid",  # type: ignore
            alpha=0.5
        )

        # 3. 自动合并检索器 (Auto-Merging)
        retriever = AutoMergingRetriever(
            vector_retriever=base_retriever,
            storage_context=storage_context,
            verbose=True
        )

        # 4. 构建引擎 (Retriever + LLM)
        query_engine = RetrieverQueryEngine.from_args(
            retriever=retriever,
            llm=self.llm,
            node_postprocessors=[self.reranker]
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