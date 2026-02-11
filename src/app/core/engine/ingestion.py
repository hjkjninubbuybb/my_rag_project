"""
[Architecture Role: Ingestion Pipeline (加工流水线)]
此模块实现了 "三权分立" 架构中的 【数据加工层】。

核心职责:
1. [ETL Process] 读取物理文件 -> 文本切片 (Chunking) -> 向量化 (Embedding) -> 存入 Qdrant。
2. [Isolation] 它只负责 "入库" 这一动作，不负责文件管理。
3. [Stateless] 它不感知 "文件状态" (SQLite)，也不负责 "清理磁盘" (rmtree)。

核心升级 (Phase 4):
1. [Strategy Injection] 文本切分策略不再硬编码，而是通过 ModelFactory 动态注入。
2. [Ablation Support] 支持通过配置文件无缝切换 "Fixed Token" vs "Recursive" 策略，
   无需修改业务代码即可运行对比实验。

数据流向:
Input (Disk: Staging) -> Processing (Memory) -> Output (Vector DB: Qdrant)
"""

from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
# 🔴 Cleanup: 移除了 TokenTextSplitter 的直接依赖，实现解耦
# from llama_index.core.node_parser import TokenTextSplitter

from app.core.engine.factory import ModelFactory
from app.core.engine.store import VectorStoreManager
# 🔴 Cleanup: 移除了 settings 依赖，具体参数由 Factory 内部处理
# from app.settings import settings
from app.utils.logger import logger


class IngestionService:
    def __init__(self):
        """
        初始化加工车间

        Architecture Note:
        - [Dependency Injection] 切分器 (NodeParser) 由 ModelFactory 统一生产。
        - [Singleton Access] 复用 StoreManager 和 Embedding 模型，减少资源开销。
        """
        # 初始化向量库管理器 (单例模式)
        self.store_manager = VectorStoreManager()
        self.embed_model = ModelFactory.get_embedding()

        # [核心组件] 文本切片器 (Text Splitter)
        #
        # Critical Change (Phase 4):
        # 之前的硬编码 TokenTextSplitter 已被移除。
        # 现在调用工厂方法，根据 YAML 配置 ("fixed" vs "recursive") 动态获取切分器。
        #
        # 论文亮点:
        # 这种 "策略模式" (Strategy Pattern) 允许系统在运行时改变算法行为，
        # 是实现科学消融实验 (Ablation Study) 的工程基础。
        self.node_parser = ModelFactory.get_text_splitter()

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
        # 使用 LlamaIndex 的标准读取器，支持多层目录递归
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
        # 这里的行为现在完全由 YAML 里的 `chunking_strategy` 决定
        # - 如果是 "fixed": 按 Token 硬切
        # - 如果是 "recursive": 按语义递归切
        nodes = self.node_parser.get_nodes_from_documents(documents)
        logger.info(f"解析完成: 共生成 {len(nodes)} 个文本切片")

        # 3. 获取存储上下文 (连接 Qdrant)
        # 注意: 这里会自动指向 settings.collection_name 指定的实验集合 (多租户隔离)
        storage_context = self.store_manager.get_storage_context()

        # 4. 将所有节点存入 DocStore (LlamaIndex 的内存/本地缓存)
        # 这一步对于后续的 "Auto-Merging Retrieval" (父子文档检索) 是必须的
        storage_context.docstore.add_documents(nodes)

        # 5. 构建索引 (Trigger Qdrant Write)
        # 这一步会触发 Embedding API 调用，并将向量写入 Qdrant
        # 稀疏向量 (Sparse Vector) 由 Store 层的 BGE-M3 适配器自动生成
        VectorStoreIndex(
            nodes,
            storage_context=storage_context,
            embed_model=self.embed_model
        )

        logger.success("文档处理与索引构建完成！(Strategy: Config-Driven)")