"""
数据入库流水线 (Ingestion Pipeline)。

接收 ExperimentConfig 进行依赖注入，通过 ComponentRegistry 获取组件。
"""

from llama_index.core import SimpleDirectoryReader, VectorStoreIndex

from rag.config.experiment import ExperimentConfig
from rag.core.registry import ComponentRegistry
from rag.storage.vectordb import VectorStoreManager
from rag.utils.logger import logger


class IngestionService:
    """数据入库服务 — 依赖注入版本。

    所有组件（切片器、Embedding）通过 ExperimentConfig + ComponentRegistry 获取，
    不再依赖 ModelFactory 或全局 settings。
    """

    def __init__(self, config: ExperimentConfig):
        self.config = config

        # 通过注册中心获取切片器
        chunker = ComponentRegistry.get_chunker(config.chunking_strategy)
        self.node_parser = chunker.create_splitter(config.chunk_size_child, config.chunk_overlap)

        # 通过注册中心获取 Embedding 模型
        embedding_provider = ComponentRegistry.get_embedding_provider(config.embedding_provider)
        self.embed_model = embedding_provider.create_embedding(
            model_name=config.embedding_model,
            api_key=config.dashscope_api_key,
        )

        # 向量库管理器
        self.store_manager = VectorStoreManager(config)

    async def process_directory(self, input_dir: str):
        """执行核心入库任务: 读取文件 -> 切片 -> Embedding -> 存入 Qdrant。"""
        logger.info(f"开始处理目录: {input_dir}")
        logger.info(
            f"配置: strategy={self.config.chunking_strategy}, "
            f"chunk_size={self.config.chunk_size_child}, "
            f"overlap={self.config.chunk_overlap}, "
            f"collection={self.config.collection_name}"
        )

        # 1. 读取文件
        documents = SimpleDirectoryReader(
            input_dir=input_dir,
            recursive=True,
            required_exts=[".pdf", ".md", ".txt"],
            encoding="utf-8",
        ).load_data()

        if not documents:
            logger.warning("未找到文档，跳过处理")
            return

        # 2. 切片
        nodes = self.node_parser.get_nodes_from_documents(documents)
        logger.info(f"解析完成: 共生成 {len(nodes)} 个文本切片")

        # 3. 获取存储上下文
        storage_context = self.store_manager.get_storage_context()

        # 4. 写入 DocStore（Auto-Merging Retrieval 需要）
        storage_context.docstore.add_documents(nodes)

        # 5. 构建索引（触发 Embedding + Qdrant 写入）
        VectorStoreIndex(
            nodes,
            storage_context=storage_context,
            embed_model=self.embed_model,
        )

        logger.success(f"文档入库完成 (collection={self.config.collection_name})")
