"""
[Architecture Role: Ingestion Pipeline (加工流水线)]
此模块实现了 "三权分立" 架构中的 【数据加工层】。

核心职责:
1. [ETL Process] 读取物理文件 -> 文本切片 (Chunking) -> 向量化 (Embedding) -> 存入 Qdrant。
2. [Isolation] 它只负责 "入库" 这一动作。
3. [Stateless] 它不感知 "文件状态" (SQLite)，也不负责 "清理磁盘" (rmtree)。

数据流向:
Input (Disk: Staging) -> Processing (Memory) -> Output (Vector DB: Qdrant)
"""

from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes

from app.core.engine.factory import ModelFactory
from app.core.engine.store import VectorStoreManager
from app.settings import settings
from app.utils.logger import logger


class IngestionService:
    def __init__(self):
        """
        初始化加工车间
        Architecture Note:
        - 仅获取 VectorStoreManager 实例来拿 storage_context，不直接调用其 delete 方法。
        - 预加载 Embedding 模型 (Factory 模式)。
        """
        # 初始化向量库管理器 (单例模式)
        self.store_manager = VectorStoreManager()
        self.embed_model = ModelFactory.get_embedding()

        # [核心组件] 层级切片器 (Hierarchical Chunking)
        # 相比普通切片，这种方式能保留父子上下文，提升检索质量
        self.node_parser = HierarchicalNodeParser.from_defaults(
            chunk_sizes=[settings.chunk_size_parent, settings.chunk_size_child]
        )

    async def process_directory(self, input_dir: str):
        """
        [Heavy Lifting] 执行核心入库任务

        Args:
            input_dir: 暂存区路径 (data/uploads/temp_batch)

        Side Effects:
            - 读取磁盘文件 (IO Read)
            - 调用 Embedding API (Network / Cost)
            - 写入 Qdrant 数据库 (DB Write)

        Critical Architecture Rule:
        此处 **严禁** 添加以下逻辑：
        1. ❌ 删除 input_dir (这是 Server.py 的职责，防止处理失败导致数据丢失)。
        2. ❌ 操作 SQLite (这是 Server.py 的职责，保持关注点分离)。
        """
        logger.info(f"开始处理目录: {input_dir}")

        # 1. 读取文件 (Source: Staging Area)
        documents = SimpleDirectoryReader(
            input_dir=input_dir,
            recursive=True,
            required_exts=[".pdf", ".md", ".txt"],
            encoding="utf-8"
        ).load_data()

        if not documents:
            logger.warning("未找到文档，跳过处理")
            return

        # 2. 生成节点树 (包含父节点和子节点)
        nodes = self.node_parser.get_nodes_from_documents(documents)

        # 3. 提取叶子节点 (最小的子块，用于计算相似度)
        leaf_nodes = get_leaf_nodes(nodes)

        logger.info(f"解析完成: 总节点 {len(nodes)} | 叶子节点 {len(leaf_nodes)}")

        # 4. 获取存储上下文 (连接 Qdrant)
        storage_context = self.store_manager.get_storage_context()

        # 5. 将所有节点存入 DocStore (LlamaIndex 的内存/本地缓存)
        storage_context.docstore.add_documents(nodes)

        # 6. 构建索引 (Trigger Qdrant Write)
        # 这一步会触发 Embedding API 调用，并将向量写入 Qdrant
        VectorStoreIndex(
            leaf_nodes,
            storage_context=storage_context,
            embed_model=self.embed_model
        )

        # [Legacy Note]
        # 旧版本 LlamaIndex 需要手动调用 persist()，
        # 新版 QdrantClient 默认自动 commit，故删除。
        # self.store_manager.persist()

        logger.success("文档处理与索引构建完成！")