"""
Qdrant 向量库管理器。

接收 ExperimentConfig 进行依赖注入。
支持 URL 模式（微服务）和本地路径模式（开发兼容）。
"""

import os
import atexit
from typing import Optional

from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core import StorageContext
from qdrant_client import QdrantClient, models

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
        """获取 StorageContext（动态绑定到 config.collection_name）。"""
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
        return StorageContext.from_defaults(vector_store=vector_store)

    def delete_file(self, file_name: str) -> bool:
        """从当前 collection 中删除指定文件的所有向量。"""
        collection = self.config.collection_name
        try:
            file_filter = models.Filter(
                should=[
                    models.FieldCondition(key="file_name", match=models.MatchValue(value=file_name)),
                    models.FieldCondition(key="metadata.file_name", match=models.MatchValue(value=file_name)),
                    models.FieldCondition(key="file_path", match=models.MatchValue(value=file_name)),
                ]
            )
            self.client.delete(
                collection_name=collection,
                points_selector=models.FilterSelector(filter=file_filter),
            )
            print(f"[Qdrant] 已清理向量: {file_name} (Collection: {collection})")
            return True
        except Exception as e:
            print(f"[Qdrant] 删除失败: {e}")
            return False

    def collection_exists(self) -> bool:
        """检查当前 collection 是否已存在。"""
        try:
            collections = self.client.get_collections().collections
            return any(c.name == self.config.collection_name for c in collections)
        except Exception:
            return False

    def collection_point_count(self) -> int:
        """获取当前 collection 中的向量数量。"""
        try:
            info = self.client.get_collection(self.config.collection_name)
            return info.points_count or 0
        except Exception:
            return 0
