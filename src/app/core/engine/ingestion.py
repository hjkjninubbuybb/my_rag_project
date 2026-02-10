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
# 👇【修改】使用 TokenTextSplitter 替代 HierarchicalNodeParser (移除 NLTK 依赖)
from llama_index.core.node_parser import TokenTextSplitter

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

        # [核心组件] 文本切片器
        # 修改为 TokenTextSplitter，彻底移除对 NLTK 的隐式依赖。
        # 这种方式按固定长度切分，对中文兼容性好，且不会因为 NLTK 分词错误导致崩溃。
        self.node_parser = TokenTextSplitter(
            chunk_size=settings.chunk_size_child,  # 复用配置 (如 512)
            chunk_overlap=50,                      # 增加一点重叠，保持上下文连续
            separator=" "                          # 备用分隔符
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

        # 2. 生成节点 (切片)
        nodes = self.node_parser.get_nodes_from_documents(documents)
        logger.info(f"解析完成: 共生成 {len(nodes)} 个文本切片")

        # 3. 获取存储上下文 (连接 Qdrant)
        storage_context = self.store_manager.get_storage_context()

        # 4. 将所有节点存入 DocStore (LlamaIndex 的内存/本地缓存)
        storage_context.docstore.add_documents(nodes)

        # 5. 构建索引 (Trigger Qdrant Write)
        # 这一步会触发 Embedding API 调用，并将向量写入 Qdrant
        # 注意：稀疏向量 (Sparse Vector) 现在由 Store 层调用 BGE-M3 自动生成
        VectorStoreIndex(
            nodes,
            storage_context=storage_context,
            embed_model=self.embed_model
        )

        logger.success("文档处理与索引构建完成！(BGE-M3 + DashScope)")