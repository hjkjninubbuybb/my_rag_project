"""
[Architecture Role: Memory (记忆)]
此模块实现了 "三权分立" 架构中的 【记忆层】。

核心职责:
1. [Vector Storage] 封装 Qdrant 向量数据库的所有底层操作。
2. [Context Provider] 为 Ingestion 和 Retrieval 提供 StorageContext。
3. [Physical Deletion] 负责从磁盘上物理清除向量数据。

架构边界:
- 它 **不负责** 维护 "已索引文件列表" (那是 Ledger/SQLite 的职责)。
- 它 **不感知** 文件的上传或暂存状态 (那是 Staging 的职责)。
"""

import os
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core import StorageContext
from qdrant_client import QdrantClient, models

from app.settings import settings
from app.core.engine.factory import ModelFactory


class VectorStoreManager:
    """
    Qdrant 向量库管理器
    Pattern: Singleton (单例模式) - 确保全应用只维护一个数据库连接。
    """
    # 单例模式
    _instance = None
    _client = None
    COLLECTION_NAME = "my_rag_collection"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VectorStoreManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """
        初始化连接
        Side Effect: 如果本地路径不存在，会自动创建目录。
        """
        if VectorStoreManager._client is not None:
            self.client = VectorStoreManager._client
            return

        if not os.path.exists(settings.qdrant_path):
            os.makedirs(settings.qdrant_path)

        print(f"🔌 [System] 正在连接 Qdrant 向量库: {settings.qdrant_path}")
        self.client = QdrantClient(path=settings.qdrant_path)
        VectorStoreManager._client = self.client

    def get_storage_context(self):
        """
        [Context Provider] 获取 LlamaIndex 存储上下文
        Usage:
        1. IngestionService 用它来写入向量。
        2. RetrievalService 用它来读取向量。
        """
        # 👇【关键修改】获取自定义的稀疏编码函数
        # 目的: 绕过 Qdrant 默认的 transformers/torch 依赖，使用轻量级 FastEmbed
        sparse_doc_fn, sparse_query_fn = ModelFactory.get_qdrant_sparse_encoders()

        vector_store = QdrantVectorStore(
            client=self.client,
            collection_name=self.COLLECTION_NAME,
            # 开启混合检索支持 (必须显式开启)
            enable_hybrid=True,
            # 👇 显式传入函数，覆盖默认的 SPLADE 行为
            sparse_doc_fn=sparse_doc_fn,
            sparse_query_fn=sparse_query_fn,
            # 批量写入优化
            batch_size=20
        )
        return StorageContext.from_defaults(vector_store=vector_store)

    def delete_file(self, file_name: str) -> bool:
        """
        [Physical Deletion] 物理删除向量

        Architecture Note:
        这是 "双重删除" 策略的一部分。当 Server 调用此方法时，
        仅仅是删除了 Qdrant 里的向量数据 (Memory)，
        Server 必须同时调用 DatabaseManager 删除元数据 (Ledger)，
        才能完成一次完整的 "文件删除" 操作。

        Implementation:
        使用 Qdrant 的 Filter Delete 机制，匹配 Payload 中的文件名。
        """
        try:
            # 定义过滤器：尝试匹配所有可能的字段 (容错处理)
            # 因为不同版本的 LlamaIndex 可能会把文件名存在不同的 key 里
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