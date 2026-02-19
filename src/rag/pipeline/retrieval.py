"""
检索引擎 (Retrieval Engine)。

接收 ExperimentConfig 进行依赖注入，所有检索参数均从 config 读取。
支持 Hybrid Search / Auto-Merging / Reranking 的灵活组合。
"""

from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import AutoMergingRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from langchain_core.tools import tool as langchain_tool
from llama_index.core.tools import QueryEngineTool, ToolMetadata

from rag.config.experiment import ExperimentConfig
from rag.core.registry import ComponentRegistry
from rag.storage.vectordb import VectorStoreManager


class RetrievalService:
    """检索服务 — 依赖注入版本。

    hybrid / auto-merge / rerank 全部由 config 控制，支持消融实验。
    """

    def __init__(self, config: ExperimentConfig):
        self.config = config
        self.store_manager = VectorStoreManager(config)

        # LLM
        llm_provider = ComponentRegistry.get_llm_provider(config.llm_provider)
        self.llm = llm_provider.create_llm(
            model_name=config.llm_model,
            api_key=config.dashscope_api_key,
            temperature=config.llm_temperature,
        )

        # Embedding
        embedding_provider = ComponentRegistry.get_embedding_provider(config.embedding_provider)
        self.embed_model = embedding_provider.create_embedding(
            model_name=config.embedding_model,
            api_key=config.dashscope_api_key,
        )

        # Reranker（可选）
        self.reranker = None
        if config.enable_rerank:
            reranker_provider = ComponentRegistry.get_reranker_provider(config.reranker_provider)
            self.reranker = reranker_provider.create_reranker(
                model_name=config.reranker_model,
                api_key=config.dashscope_api_key,
                top_n=config.rerank_top_k,
            )

    def get_retriever(self, enable_hybrid: bool = None, enable_merge: bool = None):
        """获取可配置的检索器。

        Args:
            enable_hybrid: 是否开启混合检索。默认读取 config.enable_hybrid。
            enable_merge: 是否开启自动合并检索。默认读取 config.enable_auto_merge。
        """
        if enable_hybrid is None:
            enable_hybrid = self.config.enable_hybrid
        if enable_merge is None:
            enable_merge = self.config.enable_auto_merge

        storage_context = self.store_manager.get_storage_context(enable_hybrid=enable_hybrid)
        index = VectorStoreIndex.from_vector_store(
            vector_store=storage_context.vector_store,
            storage_context=storage_context,
            embed_model=self.embed_model,
        )

        vector_mode = "hybrid" if enable_hybrid else "default"
        alpha_value = self.config.hybrid_alpha if enable_hybrid else None

        base_retriever = index.as_retriever(
            similarity_top_k=self.config.retrieval_top_k,
            vector_store_query_mode=vector_mode,
            alpha=alpha_value,
        )

        if enable_merge:
            return AutoMergingRetriever(
                vector_retriever=base_retriever,
                storage_context=storage_context,
                verbose=False,
            )
        return base_retriever

    def get_query_engine(self):
        """构建完整查询引擎（Hybrid + AutoMerge + Rerank，均由 config 控制）。"""
        storage_context = self.store_manager.get_storage_context(
            enable_hybrid=self.config.enable_hybrid,
        )
        index = VectorStoreIndex.from_vector_store(
            vector_store=storage_context.vector_store,
            storage_context=storage_context,
            embed_model=self.embed_model,
        )

        vector_mode = "hybrid" if self.config.enable_hybrid else "default"
        alpha_value = self.config.hybrid_alpha if self.config.enable_hybrid else None

        base_retriever = index.as_retriever(
            similarity_top_k=self.config.retrieval_top_k,
            vector_store_query_mode=vector_mode,  # type: ignore
            alpha=alpha_value,
        )

        if self.config.enable_auto_merge:
            retriever = AutoMergingRetriever(
                vector_retriever=base_retriever,
                storage_context=storage_context,
                verbose=True,
            )
        else:
            retriever = base_retriever

        postprocessors = []
        if self.reranker:
            postprocessors.append(self.reranker)

        query_engine = RetrieverQueryEngine.from_args(
            retriever=retriever,
            llm=self.llm,
            node_postprocessors=postprocessors,
        )
        return query_engine

    def as_langchain_tool(self):
        """转换为 LangChain Tool，供 LangGraph Agent 调用。"""
        query_engine = self.get_query_engine()
        tool = QueryEngineTool(
            query_engine=query_engine,
            metadata=ToolMetadata(
                name="knowledge_base_search",
                description="用于检索内部文档知识库。输入完整的问题进行查询。",
            ),
        )
        return tool.to_langchain_tool()

    def as_debug_langchain_tool(self):
        """创建带 debug artifact 的 LangChain Tool。

        利用 LangChain Tool Artifact 特性，在返回 LLM 消费的字符串的同时，
        将底层检索的物理分块原文、Score、来源文件名作为 artifact 旁路输出。
        """
        query_engine = self.get_query_engine()

        @langchain_tool(response_format="content_and_artifact")
        def knowledge_base_search(query: str) -> tuple[str, list[dict]]:
            """用于检索内部文档知识库。输入完整的问题进行查询。"""
            response = query_engine.query(query)

            debug_chunks = []
            for node_with_score in response.source_nodes:
                debug_chunks.append({
                    "text": node_with_score.node.text[:200],
                    "score": round(float(node_with_score.score or 0), 4),
                    "source_file": node_with_score.node.metadata.get("file_name", "unknown"),
                })

            return str(response), debug_chunks

        return knowledge_base_search
