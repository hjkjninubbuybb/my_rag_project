"""
Qdrant 向量库管理器。

支持 URL 模式（微服务）和本地路径模式（开发兼容）。
"""

import os
import atexit
from typing import Optional

from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core import StorageContext
from qdrant_client import QdrantClient, models
from sqlalchemy import create_engine, text

from app.components.providers.bgem3 import SparseModelManager


class VectorStoreManager:
    """Qdrant 向量库管理器 — 支持 URL 和本地路径模式。"""

    _shared_clients: dict[str, QdrantClient] = {}

    def __init__(self, qdrant_url: Optional[str] = None, qdrant_path: Optional[str] = None):
        """Initialize VectorStoreManager.

        Args:
            qdrant_url: Qdrant HTTP URL (e.g., "http://localhost:6333")
            qdrant_path: Qdrant local path (e.g., "data/vectordb")
        """
        # Determine endpoint (prioritize URL)
        if qdrant_url:
            endpoint = qdrant_url
        elif qdrant_path:
            endpoint = qdrant_path
        else:
            raise ValueError("Either qdrant_url or qdrant_path must be provided")

        self.endpoint = endpoint
        self.client = self._get_or_create_client(endpoint)

    @classmethod
    def _get_or_create_client(cls, endpoint: str) -> QdrantClient:
        """获取或创建 QdrantClient。支持 URL 和本地路径。"""
        if endpoint not in cls._shared_clients:
            if endpoint.startswith("http"):
                client = QdrantClient(url=endpoint)
            else:
                if not os.path.exists(endpoint):
                    os.makedirs(endpoint)
                client = QdrantClient(path=endpoint)

            cls._shared_clients[endpoint] = client
            atexit.register(cls._close_client, endpoint)

        return cls._shared_clients[endpoint]

    @classmethod
    def _close_client(cls, endpoint: str):
        client = cls._shared_clients.pop(endpoint, None)
        if client:
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

    def ensure_multimodal_collection(self) -> None:
        """确保多模态 collection 存在（支持 Named Vectors）。

        创建包含两种向量的 collection：
        - text: 1536 维（text-embedding-v4）
        - image: 2560 维（qwen3-vl-embedding）
        """
        collection_name = self.config.collection_name

        if self.client.collection_exists(collection_name):
            return

        # 创建支持 Named Vectors 的 collection
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "text": models.VectorParams(
                    size=self.config.embedding_dim,  # 1536
                    distance=models.Distance.COSINE,
                ),
                "image": models.VectorParams(
                    size=self.config.image_embedding_dim,  # 2560
                    distance=models.Distance.COSINE,
                ),
            },
        )

        print(f"[Qdrant] 创建多模态 collection: {collection_name}")
        print(f"  - text 向量: {self.config.embedding_dim} 维")
        print(f"  - image 向量: {self.config.image_embedding_dim} 维")

    def delete_file(self, file_name: str) -> bool:
        """从当前 collection 中删除指定文件的所有向量和父节点。"""
        collection = self.config.collection_name
        try:
            # 1. 删除 Qdrant 中的向量
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

            # 2. 删除 MySQL 中的父节点
            try:
                engine = create_engine(self.config.mysql_url)
                with engine.connect() as conn:
                    sql = text("""
                        DELETE FROM parent_nodes
                        WHERE collection_name = :collection_name
                        AND file_name = :file_name
                    """)
                    result = conn.execute(sql, {
                        "collection_name": collection,
                        "file_name": file_name
                    })
                    conn.commit()
                    deleted_count = result.rowcount

                engine.dispose()
                print(f"[MySQL] 已清理父节点: {deleted_count} 个 (file={file_name})")
            except Exception as e:
                print(f"[MySQL] 清理父节点失败: {e}")
                # 继续执行，不中断流程

            return True
        except Exception as e:
            print(f"[Storage] 删除失败: {e}")
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

    # ──────────────────── New API (config-free) ────────────────────

    def list_collections(self) -> list[dict]:
        """List all collections.

        Returns:
            List of dicts with name and point_count
        """
        try:
            collections = self.client.get_collections().collections
            return [
                {
                    "name": c.name,
                    "point_count": self.client.get_collection(c.name).points_count or 0,
                }
                for c in collections
            ]
        except Exception as e:
            print(f"[Qdrant] Failed to list collections: {e}")
            return []

    def add_nodes(
        self,
        nodes: list,
        collection_name: str,
        embed_model,
        enable_hybrid: bool = True,
    ):
        """Add nodes to collection.

        Args:
            nodes: List of nodes to add
            collection_name: Target collection name
            embed_model: Embedding model instance
            enable_hybrid: Enable sparse vectors
        """
        # Get sparse encoders if hybrid enabled
        if enable_hybrid:
            sparse_doc_fn, sparse_query_fn = SparseModelManager.get_sparse_encoders()
        else:
            sparse_doc_fn, sparse_query_fn = None, None

        # Create vector store
        vector_store = QdrantVectorStore(
            client=self.client,
            collection_name=collection_name,
            enable_hybrid=enable_hybrid,
            sparse_doc_fn=sparse_doc_fn,
            sparse_query_fn=sparse_query_fn,
            batch_size=20,
        )

        # Create storage context
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        # Add nodes
        storage_context.docstore.add_documents(nodes)

    def delete_collection(self, collection_name: str):
        """Delete collection.

        Args:
            collection_name: Collection name to delete
        """
        try:
            self.client.delete_collection(collection_name)
            print(f"[Qdrant] Deleted collection: {collection_name}")
        except Exception as e:
            print(f"[Qdrant] Failed to delete collection: {e}")
            raise

    def delete_by_metadata(
        self,
        collection_name: str,
        metadata_filter: dict,
    ) -> int:
        """Delete points by metadata filter.

        Args:
            collection_name: Collection name
            metadata_filter: Metadata filter dict (e.g., {"file_name": "doc.pdf"})

        Returns:
            Number of deleted points
        """
        try:
            # Build filter
            conditions = []
            for key, value in metadata_filter.items():
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value),
                    )
                )

            filter_obj = models.Filter(should=conditions)

            # Delete points
            result = self.client.delete(
                collection_name=collection_name,
                points_selector=models.FilterSelector(filter=filter_obj),
            )

            print(f"[Qdrant] Deleted points from {collection_name}: {metadata_filter}")
            return result.operation_id if hasattr(result, 'operation_id') else 0

        except Exception as e:
            print(f"[Qdrant] Failed to delete by metadata: {e}")
            raise
