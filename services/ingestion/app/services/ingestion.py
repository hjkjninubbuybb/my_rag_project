"""
数据入库流水线 (Ingestion Pipeline)。

接收 ExperimentConfig 进行依赖注入，通过 ComponentRegistry 获取组件。
"""

import json
from pathlib import Path

from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.schema import NodeRelationship

from rag_shared.config.experiment import ExperimentConfig
from rag_shared.core.registry import ComponentRegistry
from rag_shared.utils.logger import logger

from app.storage.vectordb import VectorStoreManager


class IngestionService:
    """数据入库服务 — 依赖注入版本。

    所有组件（切片器、Embedding）通过 ExperimentConfig + ComponentRegistry 获取，
    不再依赖 ModelFactory 或全局 settings。
    """

    def __init__(self, config: ExperimentConfig):
        self.config = config

        # 1. Embedding 模型（提前创建，semantic chunker 需要）
        embedding_provider = ComponentRegistry.get_embedding_provider(config.embedding_provider)
        self.embed_model = embedding_provider.create_embedding(
            model_name=config.embedding_model,
            api_key=config.dashscope_api_key,
        )

        # 2. 切片器（通过 kwargs 传递额外参数，非 semantic 策略会忽略）
        chunker = ComponentRegistry.get_chunker(config.chunking_strategy)
        self.node_parser = chunker.create_splitter(
            config.chunk_size_child,
            config.chunk_overlap,
            embed_model=self.embed_model,
            breakpoint_percentile_threshold=config.semantic_breakpoint_threshold,
            buffer_size=config.semantic_buffer_size,
        )

        # 3. 向量库管理器
        self.store_manager = VectorStoreManager(config)

    async def process_directory(self, input_dir: str):
        """执行核心入库任务: 读取文件 -> 切片 -> 序列化或向量化。"""
        logger.info(f"开始处理目录: {input_dir}")
        logger.info(
            f"配置: strategy={self.config.chunking_strategy}, "
            f"collection={self.config.collection_name}"
        )

        # 1. 读取文件
        documents = SimpleDirectoryReader(
            input_dir=input_dir,
            recursive=True,
            required_exts=[".pdf", ".md", ".txt"],
            encoding="utf-8",
        ).load_data()

        if not documents:
            logger.warning("未找到文档，跳过处理")
            return

        # 2. 切片
        nodes_result = self.node_parser.get_nodes_from_documents(documents)

        # 3. 检测是否为层级切分器（返回 tuple）
        if isinstance(nodes_result, tuple) and len(nodes_result) == 2:
            parent_nodes, child_nodes = nodes_result
            logger.info(f"层级切分: {len(parent_nodes)} 个父节点, {len(child_nodes)} 个子节点")

            # 1. 序列化到 JSON（调试 + 备份）
            json_path = self.serialize_nodes_to_json(parent_nodes, child_nodes)
            logger.info(f"✓ 节点已序列化: {json_path}")

            # 2. 向量化（父 → Docstore，子 → VectorStore）
            result = await self.vectorize_hierarchical_nodes(parent_nodes, child_nodes)

            logger.success(
                f"处理完成: {result['child_count']} 子节点已向量化, "
                f"{result['parent_count']} 父节点已存储"
            )
            return result

        else:
            # 传统扁平化切分（向后兼容）
            nodes = nodes_result
            logger.info(f"扁平化切分: 共生成 {len(nodes)} 个节点")

            # 获取存储上下文
            storage_context = self.store_manager.get_storage_context()

            # 写入 DocStore
            storage_context.docstore.add_documents(nodes)

            # 构建索引（触发 Embedding + Qdrant 写入）
            VectorStoreIndex(
                nodes,
                storage_context=storage_context,
                embed_model=self.embed_model,
            )

            logger.success(f"文档入库完成 (collection={self.config.collection_name})")

    async def process_files(self, file_paths: list):
        """处理指定文件路径列表。"""
        if not file_paths:
            logger.warning("未传入文件路径，跳过处理")
            return

        logger.info(f"开始处理 {len(file_paths)} 个指定文件")

        documents = SimpleDirectoryReader(
            input_files=file_paths,
            encoding="utf-8",
        ).load_data()

        if not documents:
            logger.warning("未找到文档内容，跳过处理")
            return

        # 切片
        nodes_result = self.node_parser.get_nodes_from_documents(documents)

        # 检测层级切分
        if isinstance(nodes_result, tuple) and len(nodes_result) == 2:
            parent_nodes, child_nodes = nodes_result
            logger.info(f"层级切分: {len(parent_nodes)} 个父节点, {len(child_nodes)} 个子节点")

            # 1. 序列化到 JSON（调试 + 备份）
            json_path = self.serialize_nodes_to_json(parent_nodes, child_nodes)
            logger.info(f"✓ 节点已序列化: {json_path}")

            # 2. 向量化（父 → Docstore，子 → VectorStore）
            result = await self.vectorize_hierarchical_nodes(parent_nodes, child_nodes)

            logger.success(
                f"处理完成: {result['child_count']} 子节点已向量化, "
                f"{result['parent_count']} 父节点已存储"
            )
            return result

        else:
            # 传统扁平化切分
            nodes = nodes_result
            logger.info(f"扁平化切分: 共生成 {len(nodes)} 个节点")

            storage_context = self.store_manager.get_storage_context()
            storage_context.docstore.add_documents(nodes)

            VectorStoreIndex(
                nodes,
                storage_context=storage_context,
                embed_model=self.embed_model,
            )

            logger.success(f"文件入库完成 (collection={self.config.collection_name})")

    def serialize_nodes_to_json(
        self,
        parent_nodes: list,
        child_nodes: list,
        output_path: str | None = None
    ) -> str:
        """
        序列化父子节点到 JSON 文件。

        Args:
            parent_nodes: 父节点列表
            child_nodes: 子节点列表
            output_path: 输出路径（可选，默认自动生成）

        Returns:
            str: JSON 文件路径
        """
        if output_path is None:
            # 使用 collection_name 作为文件名
            output_dir = Path("D:/Projects/my_rag_project/data/parsed_nodes")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"{self.config.collection_name}.json")

        # 序列化父节点
        parent_data = []
        for node in parent_nodes:
            parent_data.append({
                "id": node.id_,
                "text": node.text,
                "metadata": node.metadata,
                "type": "parent",
            })

        # 序列化子节点
        child_data = []
        for node in child_nodes:
            # 提取 parent relationship
            parent_info = node.relationships.get(NodeRelationship.PARENT)
            parent_id = parent_info.node_id if parent_info else None

            child_data.append({
                "id": node.id_,
                "text": node.text,
                "index_id": node.index_id,  # IndexNode 特有
                "metadata": node.metadata,
                "parent_id": parent_id,
                "type": "child",
            })

        # 组装完整数据
        data = {
            "collection_name": self.config.collection_name,
            "chunking_strategy": self.config.chunking_strategy,
            "parent_count": len(parent_nodes),
            "child_count": len(child_nodes),
            "parents": parent_data,
            "children": child_data,
        }

        # 写入 JSON
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"✓ 节点已序列化: {output_path}")
        logger.info(f"  - 父节点: {len(parent_nodes)} 个")
        logger.info(f"  - 子节点: {len(child_nodes)} 个")

        return str(output_path)

    async def vectorize_hierarchical_nodes(
        self,
        parent_nodes: list,
        child_nodes: list,
    ) -> dict:
        """
        向量化层级节点。

        Args:
            parent_nodes: 父节点列表（TextNode）
            child_nodes: 子节点列表（IndexNode）

        Returns:
            dict: {
                "parent_count": int,
                "child_count": int,
                "vectorized_count": int,
                "collection_name": str
            }
        """
        logger.info(f"开始向量化: {len(parent_nodes)} 父 + {len(child_nodes)} 子")

        # 1. 获取存储上下文
        storage_context = self.store_manager.get_storage_context()

        # 2. 父节点 → Docstore（不向量化）
        logger.info(f"存储 {len(parent_nodes)} 个父节点到 Docstore...")
        storage_context.docstore.add_documents(parent_nodes)

        # 3. 子节点 → VectorStore（向量化）
        logger.info(f"向量化 {len(child_nodes)} 个子节点...")
        VectorStoreIndex(
            child_nodes,
            storage_context=storage_context,
            embed_model=self.embed_model,
            show_progress=True,
        )

        # 4. 验证
        point_count = self.store_manager.collection_point_count()
        logger.success(
            f"向量化完成: {point_count} 个向量 (collection={self.config.collection_name})"
        )

        return {
            "parent_count": len(parent_nodes),
            "child_count": len(child_nodes),
            "vectorized_count": point_count,
            "collection_name": self.config.collection_name,
        }
