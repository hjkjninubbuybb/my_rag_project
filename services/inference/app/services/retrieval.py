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

from rag_shared.config.experiment import ExperimentConfig
from rag_shared.core.registry import ComponentRegistry
from app.storage.vectordb import VectorStoreManager
from app.storage.mysql_client import MySQLClient


class RetrievalService:
    """检索服务 — 依赖注入版本。

    hybrid / auto-merge / rerank 全部由 config 控制，支持消融实验。
    """

    def __init__(self, config: ExperimentConfig):
        self.config = config
        self.store_manager = VectorStoreManager(config)

        # MySQL 客户端（用于查询父节点）
        self.mysql_client = None
        if config.enable_multimodal:
            try:
                self.mysql_client = MySQLClient(
                    host=config.mysql_host,
                    port=config.mysql_port,
                    user=config.mysql_user,
                    password=config.mysql_password,
                    database=config.mysql_database
                )
                self.mysql_client.connect()
            except Exception as e:
                print(f"[Warning] MySQL 连接失败: {e}，多模态检索将不可用")

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
        """获取可配置的检索器。"""
        if enable_hybrid is None:
            enable_hybrid = self.config.enable_hybrid
        if enable_merge is None:
            enable_merge = self.config.enable_auto_merge

        # 动态调整 top_k（sentence 策略需要更大的 top_k）
        top_k = self.config.retrieval_top_k
        if self.config.chunking_strategy == "sentence" and top_k < 10:
            top_k = max(10, top_k)
            print(f"[Retrieval] sentence 策略自动调整 top_k: {self.config.retrieval_top_k} → {top_k}")

        storage_context = self.store_manager.get_storage_context(enable_hybrid=enable_hybrid)
        index = VectorStoreIndex.from_vector_store(
            vector_store=storage_context.vector_store,
            storage_context=storage_context,
            embed_model=self.embed_model,
        )

        vector_mode = "hybrid" if enable_hybrid else "default"
        alpha_value = self.config.hybrid_alpha if enable_hybrid else None

        base_retriever = index.as_retriever(
            similarity_top_k=top_k,
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
        # 动态调整 top_k（sentence 策略需要更大的 top_k）
        top_k = self.config.retrieval_top_k
        if self.config.chunking_strategy == "sentence" and top_k < 10:
            top_k = max(10, top_k)
            print(f"[Retrieval] sentence 策略自动调整 top_k: {self.config.retrieval_top_k} → {top_k}")

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
            similarity_top_k=top_k,
            vector_store_query_mode=vector_mode,
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

        针对 sentence 策略的层级结构优化：
        - 如果启用 Auto-Merge，展示合并后的父节点信息
        - 同时保留原始子节点的检索信息（header_path、sentence_index）
        - 提供更详细的 debug 数据用于分析检索质量

        多模态支持：
        - 检测 image_summary 类型的节点
        - 自动获取父节点中的原始图片数据
        - 在 artifact 中返回图片信息供 VLM 使用
        """
        query_engine = self.get_query_engine()

        @langchain_tool(response_format="content_and_artifact")
        def knowledge_base_search(query: str) -> tuple[str, list[dict]]:
            """用于检索内部文档知识库。输入完整的问题进行查询。"""
            response = query_engine.query(query)

            debug_chunks = []
            parent_ids_to_fetch = []

            for node_with_score in response.source_nodes:
                node = node_with_score.node
                metadata = node.metadata

                # 判断节点类型
                node_type = metadata.get("node_type", "flat")
                is_parent = False

                # 检测是否为父节点（Auto-Merge 后的结果）
                if metadata.get("header_path") and len(node.text) > 500:
                    node_type = "parent"
                    is_parent = True
                elif "sentence_index" in metadata:
                    node_type = "child"

                # 检测多模态节点
                is_multimodal = node_type == "image_summary"
                if is_multimodal:
                    parent_id = metadata.get("parent_id")
                    if parent_id and parent_id not in parent_ids_to_fetch:
                        parent_ids_to_fetch.append(parent_id)

                # 构建 debug chunk
                chunk_info = {
                    "text": node.text[:300] if is_parent else node.text[:200],
                    "full_text_length": len(node.text),
                    "score": round(float(node_with_score.score or 0), 4),
                    "source_file": metadata.get("file_name", "unknown"),
                    "header_path": metadata.get("header_path", ""),
                    "node_type": node_type,
                    "is_merged": is_parent,
                    "is_multimodal": is_multimodal,
                }

                # 如果是子节点，添加额外信息
                if node_type == "child":
                    chunk_info["sentence_index"] = metadata.get("sentence_index", -1)
                    chunk_info["parent_id"] = metadata.get("parent_id", "")

                # 如果是多模态节点，添加图片元信息
                if is_multimodal:
                    chunk_info["parent_id"] = metadata.get("parent_id", "")
                    chunk_info["image_type"] = metadata.get("image_type", "other")
                    chunk_info["image_index"] = metadata.get("image_index", 0)

                debug_chunks.append(chunk_info)

            # 如果检测到多模态节点，获取父节点中的图片
            if parent_ids_to_fetch and self.mysql_client:
                try:
                    parent_nodes = self.mysql_client.get_nodes_by_ids(
                        node_ids=parent_ids_to_fetch,
                        collection_name=self.config.collection_name
                    )

                    # 将图片数据添加到对应的 chunk_info 中
                    parent_map = {node["node_id"]: node for node in parent_nodes}

                    for chunk_info in debug_chunks:
                        if chunk_info.get("is_multimodal"):
                            parent_id = chunk_info.get("parent_id")
                            if parent_id in parent_map:
                                parent_node = parent_map[parent_id]
                                images = parent_node.get("metadata", {}).get("images", [])
                                img_idx = chunk_info.get("image_index", 0)

                                if img_idx < len(images):
                                    chunk_info["image_data"] = images[img_idx]

                except Exception as e:
                    print(f"[Warning] 获取多模态父节点失败: {e}")

            return str(response), debug_chunks

        return knowledge_base_search

    def retrieve_with_images(self, query: str, top_k: int = None):
        """两阶段检索：先检索摘要文本，再获取原图。

        Args:
            query: 查询文本
            top_k: 检索数量（默认使用 config 配置）

        Returns:
            tuple: (text_nodes, parent_nodes_with_images)
            - text_nodes: 检索到的子节点（摘要文本）
            - parent_nodes_with_images: 父节点列表（包含原图 base64）
        """
        if not self.config.enable_multimodal or not self.mysql_client:
            raise RuntimeError("多模态检索未启用或 MySQL 连接失败")

        # 阶段 1: 检索子节点（摘要文本）
        retriever = self.get_retriever()
        if top_k is None:
            top_k = self.config.retrieval_top_k

        child_nodes = retriever.retrieve(query)

        # 阶段 2: 提取 parent_ids 并批量查询父节点
        parent_ids = []
        for node in child_nodes:
            parent_id = node.metadata.get("parent_id")
            if parent_id and parent_id not in parent_ids:
                parent_ids.append(parent_id)

        if not parent_ids:
            return child_nodes, []

        # 从 MySQL 批量查询父节点
        parent_nodes = self.mysql_client.get_nodes_by_ids(
            node_ids=parent_ids,
            collection_name=self.config.collection_name
        )

        return child_nodes, parent_nodes
