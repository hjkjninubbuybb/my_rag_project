import os
import atexit
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core import StorageContext
from qdrant_client import QdrantClient, models

from app.settings import settings
from app.core.engine.factory import ModelFactory


class VectorStoreManager:
    """
    Qdrant 向量库管理器 - Phase 3 Safety Enhanced
    """
    _instance = None
    _client = None
    _initialized = False  # 🔴 Safety: 防止 __init__ 重复执行

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VectorStoreManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        # 🔴 Safety: 只有第一次初始化时才执行逻辑
        if VectorStoreManager._initialized:
            return

        # 复用 Client (防止多重连接)
        if VectorStoreManager._client is not None:
            self.client = VectorStoreManager._client
        else:
            if not os.path.exists(settings.qdrant_path):
                os.makedirs(settings.qdrant_path)

            print(f"🔌 [System] 连接向量库: {settings.qdrant_path}")
            self.client = QdrantClient(path=settings.qdrant_path)
            VectorStoreManager._client = self.client

            # 🔴 Safety: 只注册一次退出钩子
            atexit.register(self.close_connection)

        VectorStoreManager._initialized = True

    def close_connection(self):
        if self.client:
            print("🔌 [System] 关闭 Qdrant 连接...")
            try:
                self.client.close()
            except Exception:
                pass
            finally:
                VectorStoreManager._client = None
                self.client = None
                VectorStoreManager._initialized = False

    def get_storage_context(self):
        """获取上下文 (动态绑定 Collection)"""
        sparse_doc_fn, sparse_query_fn = ModelFactory.get_qdrant_sparse_encoders()
        current_collection = settings.collection_name

        # LlamaIndex 的 QdrantVectorStore 是轻量级封装，
        # 每次创建新实例指向不同 collection 是安全的且开销极低。
        vector_store = QdrantVectorStore(
            client=self.client,
            collection_name=current_collection,
            enable_hybrid=True,
            sparse_doc_fn=sparse_doc_fn,
            sparse_query_fn=sparse_query_fn,
            batch_size=20
        )
        return StorageContext.from_defaults(vector_store=vector_store)

    def delete_file(self, file_name: str) -> bool:
        """物理删除 (动态绑定 Collection)"""
        current_collection = settings.collection_name
        try:
            file_filter = models.Filter(
                should=[
                    models.FieldCondition(key="file_name", match=models.MatchValue(value=file_name)),
                    models.FieldCondition(key="metadata.file_name", match=models.MatchValue(value=file_name)),
                    models.FieldCondition(key="file_path", match=models.MatchValue(value=file_name)),
                ]
            )

            self.client.delete(
                collection_name=current_collection,
                points_selector=models.FilterSelector(filter=file_filter)
            )
            print(f"🗑️ [Qdrant] 已清理向量: {file_name} (Collection: {current_collection})")
            return True
        except Exception as e:
            print(f"❌ [Qdrant] 删除失败: {e}")
            return False