"""
Qdrant 向量库管理器（Inference 服务 — 只读向）。

接收 ExperimentConfig 进行依赖注入。
支持 URL 模式（微服务）和本地路径模式（开发兼容）。
"""

import os
import json
import atexit
from typing import Optional

from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core import StorageContext
from llama_index.core.schema import TextNode
from qdrant_client import QdrantClient
from sqlalchemy import create_engine, text

from rag_shared.config.experiment import ExperimentConfig
from app.components.providers.bgem3 import SparseModelManager


class VectorStoreManager:
    """Qdrant 向量库管理器 — 支持 URL 和本地路径模式。"""

    _shared_clients: dict[str, QdrantClient] = {}

    def __init__(self, config: ExperimentConfig):
        self.config = config
        self.client = self._get_or_create_client(config.qdrant_endpoint)

    @classmethod
    def _get_or_create_client(cls, endpoint: str) -> QdrantClient:
        """获取或创建 QdrantClient。支持 URL 和本地路径。"""
        if endpoint not in cls._shared_clients:
            if endpoint.startswith("http"):
                print(f"[System] 连接向量库: {endpoint}")
                client = QdrantClient(url=endpoint)
            else:
                if not os.path.exists(endpoint):
                    os.makedirs(endpoint)
                print(f"[System] 连接向量库 (本地): {endpoint}")
                client = QdrantClient(path=endpoint)

            cls._shared_clients[endpoint] = client
            atexit.register(cls._close_client, endpoint)

        return cls._shared_clients[endpoint]

    @classmethod
    def _close_client(cls, endpoint: str):
        client = cls._shared_clients.pop(endpoint, None)
        if client:
            print(f"[System] 关闭 Qdrant 连接: {endpoint}")
            try:
                client.close()
            except Exception:
                pass

    def get_storage_context(self, enable_hybrid: Optional[bool] = None) -> StorageContext:
        """获取 StorageContext（动态绑定到 config.collection_name）。

        如果是 sentence 策略，自动从 MySQL 重建 docstore。
        """
        hybrid = enable_hybrid if enable_hybrid is not None else self.config.enable_hybrid

        if hybrid:
            sparse_doc_fn, sparse_query_fn = SparseModelManager.get_sparse_encoders()
        else:
            sparse_doc_fn, sparse_query_fn = None, None

        vector_store = QdrantVectorStore(
            client=self.client,
            collection_name=self.config.collection_name,
            enable_hybrid=hybrid,
            sparse_doc_fn=sparse_doc_fn,
            sparse_query_fn=sparse_query_fn,
            batch_size=20,
        )

        # 创建 storage_context
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        # 如果是 sentence 策略且启用 auto_merge，从 MySQL 重建 docstore
        if self.config.chunking_strategy == "sentence" and self.config.enable_auto_merge:
            self.rebuild_docstore_from_mysql(storage_context)

        return storage_context

    def rebuild_docstore_from_mysql(self, storage_context: StorageContext) -> int:
        """从 MySQL 重建 Docstore（加载父节点）。

        Returns:
            int: 加载的父节点数量
        """
        try:
            engine = create_engine(self.config.mysql_url)

            with engine.connect() as conn:
                # 查询当前 collection 的所有父节点
                sql = text("""
                    SELECT id, text, metadata
                    FROM parent_nodes
                    WHERE collection_name = :collection_name
                """)
                result = conn.execute(sql, {"collection_name": self.config.collection_name})

                parent_count = 0
                for row in result:
                    # 反序列化 metadata
                    metadata = json.loads(row.metadata) if row.metadata else {}

                    # 重建 TextNode
                    node = TextNode(
                        id_=row.id,
                        text=row.text,
                        metadata=metadata,
                    )

                    # 添加到 docstore
                    storage_context.docstore.add_documents([node])
                    parent_count += 1

            engine.dispose()
            print(f"[Inference] 已从 MySQL 加载 {parent_count} 个父节点到 Docstore")
            return parent_count

        except Exception as e:
            print(f"[Inference] 从 MySQL 重建 Docstore 失败: {e}")
            return 0
