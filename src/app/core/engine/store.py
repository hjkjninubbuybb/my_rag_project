import os
from typing import Optional

from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.core import StorageContext
from qdrant_client import QdrantClient

from app.settings import settings


class VectorStoreManager:
    """
    存储管理器：管理数据库连接与持久化
    """

    def __init__(
            self,
            qdrant_path: Optional[str] = None,
            collection_name: Optional[str] = None,
            storage_dir: Optional[str] = None
    ):
        # 支持依赖注入，方便测试
        self.qdrant_path = qdrant_path or settings.qdrant_path
        self.collection_name = collection_name or settings.qdrant_collection
        self.storage_dir = storage_dir or settings.storage_dir

        # 1. 初始化 Qdrant 客户端
        if self.qdrant_path == ":memory:":
            self.client = QdrantClient(location=":memory:")
        else:
            self.client = QdrantClient(path=self.qdrant_path)

        # 2. 初始化 Vector Store
        self.vector_store = QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name
        )

        # 3. 初始化 DocStore (用于自动合并检索)
        self.doc_store = self._init_doc_store()

    def _init_doc_store(self) -> SimpleDocumentStore:
        """尝试从本地加载 DocStore，失败则新建"""
        if self.storage_dir == ":memory:":
            return SimpleDocumentStore()

        json_path = os.path.join(self.storage_dir, "docstore.json")
        if os.path.exists(json_path):
            return SimpleDocumentStore.from_persist_dir(persist_dir=self.storage_dir)
        return SimpleDocumentStore()

    def get_storage_context(self) -> StorageContext:
        """返回 LlamaIndex 标准存储上下文"""
        return StorageContext.from_defaults(
            vector_store=self.vector_store,
            docstore=self.doc_store
        )

    def persist(self):
        """手动保存 DocStore 到磁盘"""
        if self.storage_dir != ":memory:":
            self.doc_store.persist(persist_dir=self.storage_dir)