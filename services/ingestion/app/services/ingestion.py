"""
数据入库流水线 (Ingestion Pipeline)。

接收 ExperimentConfig 进行依赖注入，通过 ComponentRegistry 获取组件。
"""

import json
from pathlib import Path

from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.schema import NodeRelationship
from sqlalchemy import create_engine, text

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

        新策略：
        - 子节点 → Qdrant（向量化）
        - 父节点 → MySQL（持久化存储）

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
        logger.info(f"开始处理: {len(parent_nodes)} 父 + {len(child_nodes)} 子")

        # 1. 获取存储上下文
        storage_context = self.store_manager.get_storage_context()

        # 2. 父节点 → Docstore（保持原有逻辑，用于 JSON 序列化）
        logger.info(f"存储 {len(parent_nodes)} 个父节点到 Docstore...")
        storage_context.docstore.add_documents(parent_nodes)

        # 3. 父节点 → MySQL
        logger.info(f"存储 {len(parent_nodes)} 个父节点到 MySQL...")
        try:
            engine = create_engine(self.config.mysql_url)

            with engine.connect() as conn:
                for parent in parent_nodes:
                    # 准备数据
                    node_data = {
                        "id": parent.id_,
                        "collection_name": self.config.collection_name,
                        "file_name": parent.metadata.get("file_name", ""),
                        "text": parent.text,
                        "metadata": json.dumps(parent.metadata, ensure_ascii=False),
                    }

                    # 使用 INSERT ... ON DUPLICATE KEY UPDATE（MySQL 特性）
                    sql = text("""
                        INSERT INTO parent_nodes (id, collection_name, file_name, text, metadata)
                        VALUES (:id, :collection_name, :file_name, :text, :metadata)
                        ON DUPLICATE KEY UPDATE
                            text = VALUES(text),
                            metadata = VALUES(metadata),
                            updated_at = CURRENT_TIMESTAMP
                    """)
                    conn.execute(sql, node_data)

                conn.commit()

            engine.dispose()
            logger.info(f"✓ 父节点已存入 MySQL: {self.config.collection_name}")
        except Exception as e:
            logger.error(f"存储父节点到 MySQL 失败: {e}")
            # 继续执行，不中断流程

        # 4. 子节点 → VectorStore（向量化）
        logger.info(f"向量化 {len(child_nodes)} 个子节点...")
        VectorStoreIndex(
            child_nodes,
            storage_context=storage_context,
            embed_model=self.embed_model,
            show_progress=True,
        )

        # 5. 验证
        point_count = self.store_manager.collection_point_count()
        logger.success(
            f"处理完成: {point_count} 个向量 (子节点), "
            f"{len(parent_nodes)} 个父节点 (MySQL)"
        )

        return {
            "parent_count": len(parent_nodes),
            "child_count": len(child_nodes),
            "vectorized_count": point_count,
            "collection_name": self.config.collection_name,
        }

    async def process_multimodal_documents(self, pdf_bytes: bytes, filename: str) -> dict:
        """处理多模态文档（PDF 图文对）。

        流程：
        1. 使用 MultimodalPDFParser 提取图文对
        2. 构建包含 multimodal_chunks 的 Document
        3. 使用 MultimodalChunker 切分父子节点
        4. 图像预处理（压缩、Hash）
        5. 生成图像 embedding
        6. 向量化入库

        Args:
            pdf_bytes: PDF 文件二进制数据。
            filename: 文件名。

        Returns:
            dict: 处理结果统计。
        """
        from llama_index.core import Document
        from app.parsing.multimodal_parser import MultimodalPDFParser
        from app.components.processors.image import DefaultImageProcessor

        logger.info(f"开始处理多模态文档: {filename}")

        # 1. 确保多模态 collection 存在
        self.store_manager.ensure_multimodal_collection()

        # 2. 解析 PDF 图文对
        parser = MultimodalPDFParser()
        multimodal_chunks = parser.parse(pdf_bytes, filename)

        logger.info(
            f"PDF 解析完成: {len(multimodal_chunks)} 页, "
            f"总图片数: {sum(len(c['images']) for c in multimodal_chunks)}"
        )

        # 3. 构建 Document
        doc = Document(
            text="",  # 占位
            metadata={
                "file_name": filename,
                "multimodal_chunks": multimodal_chunks,
                "role": multimodal_chunks[0]["role"] if multimodal_chunks else "common",
            },
        )

        # 4. 使用 MultimodalChunker 切分
        multimodal_chunker = ComponentRegistry.get_chunker("multimodal")
        splitter = multimodal_chunker.create_splitter(
            chunk_size=0,  # 未使用
            chunk_overlap=0,
            api_key=self.config.dashscope_api_key,
            vlm_model=self.config.multimodal_llm_model,
            enable_vlm_summary=True,
        )
        parent_nodes, child_nodes = splitter.get_nodes_from_documents([doc])

        logger.info(f"多模态切分完成: {len(parent_nodes)} 父节点, {len(child_nodes)} 子节点")

        # 5. 图像预处理
        image_processor = DefaultImageProcessor()

        for child in child_nodes:
            if "_image_bytes" in child.metadata:
                raw_bytes = child.metadata["_image_bytes"]

                # 压缩
                processed_bytes = image_processor.preprocess(
                    raw_bytes,
                    max_size=self.config.image_max_size,
                    quality=self.config.image_compression_quality,
                )

                # 计算 Hash（去重）
                image_hash = image_processor.extract_hash(processed_bytes)

                # 更新 metadata
                child.metadata["_image_bytes"] = processed_bytes  # 更新为压缩后的
                child.metadata["image_hash"] = image_hash

        logger.info(f"图像预处理完成: {len(child_nodes)} 张图片")

        # 6. 生成图像 embedding
        # 获取多模态 embedding provider
        mm_provider_class = ComponentRegistry.get_multimodal_embedding_provider(
            self.config.multimodal_embedding_provider
        )
        mm_embed_provider = mm_provider_class(api_key=self.config.dashscope_api_key)

        # 批量生成图像 embedding
        image_bytes_list = [
            child.metadata["_image_bytes"]
            for child in child_nodes
            if "_image_bytes" in child.metadata
        ]

        if image_bytes_list:
            logger.info(f"生成图像 embedding: {len(image_bytes_list)} 张图片")
            image_embeddings = mm_embed_provider.embed_images_from_bytes(image_bytes_list)

            # 将 embedding 附加到子节点
            for i, child in enumerate(child_nodes):
                if "_image_bytes" in child.metadata:
                    child.embedding = image_embeddings[i]

                    # 清理临时数据（不需要存储到 Qdrant）
                    del child.metadata["_image_bytes"]

            logger.info(f"图像 embedding 完成: {len(image_embeddings)} 个向量 (2560 维)")

        # 7. 向量化入库（复用现有逻辑，但需要特殊处理多模态向量）
        result = await self._vectorize_multimodal_nodes(parent_nodes, child_nodes)

        logger.success(
            f"多模态文档处理完成: {result['child_count']} 子节点已向量化, "
            f"{result['parent_count']} 父节点已存储"
        )

        return result

    async def _vectorize_multimodal_nodes(
        self,
        parent_nodes: list,
        child_nodes: list,
    ) -> dict:
        """向量化多模态节点（包含图像向量）。

        与 vectorize_hierarchical_nodes 类似，但：
        - 父节点存储到 MySQL 时标记 collection_type="multimodal", node_format="mixed"
        - 子节点使用预先计算的 image embedding（不使用 text embedding）

        Args:
            parent_nodes: 父节点列表（包含图文对）。
            child_nodes: 子节点列表（已附加 image embedding）。

        Returns:
            dict: 处理结果。
        """
        logger.info(f"开始向量化多模态节点: {len(parent_nodes)} 父 + {len(child_nodes)} 子")

        # 1. 父节点 → MySQL
        try:
            engine = create_engine(self.config.mysql_url)

            with engine.connect() as conn:
                for parent in parent_nodes:
                    node_data = {
                        "id": parent.id_,
                        "collection_name": self.config.collection_name,
                        "collection_type": "multimodal",
                        "node_format": parent.metadata.get("node_format", "mixed"),
                        "file_name": parent.metadata.get("file_name", ""),
                        "text": parent.text,
                        "metadata": json.dumps(parent.metadata, ensure_ascii=False),
                    }

                    sql = text("""
                        INSERT INTO parent_nodes
                        (id, collection_name, collection_type, node_format, file_name, text, metadata)
                        VALUES (:id, :collection_name, :collection_type, :node_format, :file_name, :text, :metadata)
                        ON DUPLICATE KEY UPDATE
                            text = VALUES(text),
                            metadata = VALUES(metadata),
                            collection_type = VALUES(collection_type),
                            node_format = VALUES(node_format),
                            updated_at = CURRENT_TIMESTAMP
                    """)
                    conn.execute(sql, node_data)

                conn.commit()

            engine.dispose()
            logger.info(f"✓ 多模态父节点已存入 MySQL: {len(parent_nodes)} 个")

        except Exception as e:
            logger.error(f"存储多模态父节点失败: {e}")

        # 2. 子节点 → Qdrant（使用预先计算的 image embedding）
        # 注意：由于 child_nodes 已有 embedding，直接插入到 Qdrant
        # 需要手动构建 points，因为 VectorStoreIndex 会重新计算 embedding

        from qdrant_client import models

        points = []
        for child in child_nodes:
            if not hasattr(child, "embedding") or child.embedding is None:
                logger.warning(f"子节点 {child.id_} 缺少 embedding，跳过")
                continue

            # 构建 Qdrant Point（使用 Named Vectors）
            point = models.PointStruct(
                id=child.id_,
                vector={
                    "image": child.embedding,  # 2560 维图像向量
                },
                payload={
                    "text": child.text,
                    "file_name": child.metadata.get("file_name", ""),
                    "page": child.metadata.get("page", 0),
                    "role": child.metadata.get("role", "common"),
                    "node_type": child.metadata.get("node_type", "image"),
                    "parent_id": child.metadata.get("parent_id", ""),
                    "image_index": child.metadata.get("image_index", 0),
                    "image_hash": child.metadata.get("image_hash", ""),
                },
            )
            points.append(point)

        # 批量插入
        if points:
            self.store_manager.client.upsert(
                collection_name=self.config.collection_name,
                points=points,
            )
            logger.info(f"✓ 多模态子节点已存入 Qdrant: {len(points)} 个")

        # 3. 验证
        point_count = self.store_manager.collection_point_count()
        logger.success(
            f"多模态处理完成: {point_count} 个向量, "
            f"{len(parent_nodes)} 个父节点"
        )

        return {
            "parent_count": len(parent_nodes),
            "child_count": len(child_nodes),
            "vectorized_count": len(points),
            "collection_name": self.config.collection_name,
        }
