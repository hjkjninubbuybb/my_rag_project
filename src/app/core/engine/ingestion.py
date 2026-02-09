from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes

from app.core.engine.factory import ModelFactory
from app.core.engine.store import VectorStoreManager
from app.settings import settings
from app.utils.logger import logger


class IngestionService:
    def __init__(self):
        # 初始化向量库管理器 (单例模式)
        self.store_manager = VectorStoreManager()
        self.embed_model = ModelFactory.get_embedding()

        # [核心组件] 层级切片器
        self.node_parser = HierarchicalNodeParser.from_defaults(
            chunk_sizes=[settings.chunk_size_parent, settings.chunk_size_child]
        )

    async def process_directory(self, input_dir: str):
        """
        处理指定目录下的所有文件并构建索引
        """
        logger.info(f"开始处理目录: {input_dir}")

        # 1. 读取文件
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

        # 3. 提取叶子节点 (最小的子块)
        leaf_nodes = get_leaf_nodes(nodes)

        logger.info(f"解析完成: 总节点 {len(nodes)} | 叶子节点 {len(leaf_nodes)}")

        # 4. 获取存储上下文
        storage_context = self.store_manager.get_storage_context()

        # 5. 将所有节点存入 DocStore (内存中暂存)
        storage_context.docstore.add_documents(nodes)

        # 6. 构建索引 (这一步会自动将向量写入 Qdrant 数据库)
        VectorStoreIndex(
            leaf_nodes,
            storage_context=storage_context,
            embed_model=self.embed_model
        )

        # 7. 持久化保存 (❌ 删除这一行，Qdrant 会自动保存)
        # self.store_manager.persist()

        logger.success("文档处理与索引构建完成！")