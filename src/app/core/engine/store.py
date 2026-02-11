import os
import atexit  # 👈 1. 新增导入
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
        # 单例检查：如果已经有 client 了，直接复用
        if VectorStoreManager._client is not None:
            self.client = VectorStoreManager._client
            return

        if not os.path.exists(settings.qdrant_path):
            os.makedirs(settings.qdrant_path)

        print(f"🔌 [System] 正在连接 Qdrant 向量库: {settings.qdrant_path}")
        self.client = QdrantClient(path=settings.qdrant_path)
        VectorStoreManager._client = self.client

        # 👇 2. 注册退出钩子：程序死掉前，强制执行 close()
        # 这一步是解决 "LockError" 的关键
        atexit.register(self.close_connection)

    def close_connection(self):  # 👈 3. 新增关闭方法
        """
        [Resource Cleanup] 显式关闭连接，释放文件锁
        Trigger: 程序退出时 (atexit) 自动调用
        """
        if self.client:
            print("🔌 [System] 正在关闭 Qdrant 连接，释放资源...")
            try:
                self.client.close()
                print("✅ [System] Qdrant 连接已安全关闭。")
            except Exception as e:
                print(f"⚠️ [System] 关闭 Qdrant 时发生警告: {e}")
            finally:
                # 清理类变量，防止单例残留
                VectorStoreManager._client = None
                self.client = None

    def get_storage_context(self):
        """
        [Context Provider] 获取 LlamaIndex 存储上下文
        Usage:
        1. IngestionService 用它来写入向量。
        2. RetrievalService 用它来读取向量。
        """
        # 获取自定义的稀疏编码函数
        # 目的: 绕过 Qdrant 默认的 transformers/torch 依赖，使用轻量级 FastEmbed
        sparse_doc_fn, sparse_query_fn = ModelFactory.get_qdrant_sparse_encoders()

        vector_store = QdrantVectorStore(
            client=self.client,
            collection_name=self.COLLECTION_NAME,
            # 开启混合检索支持 (必须显式开启)
            enable_hybrid=True,
            # 显式传入函数，覆盖默认的 SPLADE 行为
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