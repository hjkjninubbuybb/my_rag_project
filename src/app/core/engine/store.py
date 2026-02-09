import os
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core import StorageContext
from qdrant_client import QdrantClient, models

from app.settings import settings


class VectorStoreManager:
    # 单例模式
    _instance = None
    _client = None
    COLLECTION_NAME = "my_rag_collection"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VectorStoreManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if VectorStoreManager._client is not None:
            self.client = VectorStoreManager._client
            return

        if not os.path.exists(settings.qdrant_path):
            os.makedirs(settings.qdrant_path)

        print(f"🔌 [System] 正在连接 Qdrant 向量库: {settings.qdrant_path}")
        self.client = QdrantClient(path=settings.qdrant_path)
        VectorStoreManager._client = self.client

    def get_storage_context(self):
        """获取 LlamaIndex 存储上下文"""
        vector_store = QdrantVectorStore(
            client=self.client,
            collection_name=self.COLLECTION_NAME
        )
        return StorageContext.from_defaults(vector_store=vector_store)

    def delete_file(self, file_name: str) -> bool:
        """
        [物理删除] 从 Qdrant 中删除指定文件的所有向量
        """
        try:
            # 定义过滤器：尝试匹配所有可能的字段
            file_filter = models.Filter(
                should=[
                    models.FieldCondition(key="file_name", match=models.MatchValue(value=file_name)),
                    models.FieldCondition(key="metadata.file_name", match=models.MatchValue(value=file_name)),
                    # 兼容可能存在的 full path 记录
                    models.FieldCondition(key="file_path", match=models.MatchValue(value=file_name)),
                ]
            )

            self.client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=models.FilterSelector(filter=file_filter)
            )
            print(f"🗑️ [Qdrant] 已清理向量数据: {file_name}")
            return True
        except Exception as e:
            print(f"❌ [Qdrant] 删除失败: {e}")
            return False