"""
[Architecture Role: Ingestion Pipeline (加工流水线)]
此模块实现了 "三权分立" 架构中的 【数据加工层】。

核心职责:
1. [ETL Process] 读取物理文件 -> 文本切片 (Chunking) -> 向量化 (Embedding) -> 存入 Qdrant。
2. [Isolation] 它只负责 "入库" 这一动作，不负责文件管理。
3. [Debugging] 内置了详细的性能监控日志，用于排查卡顿问题。
"""

import time
import logging
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from app.core.engine.factory import ModelFactory
from app.core.engine.store import VectorStoreManager
from app.utils.logger import logger

# 获取全局 logger 以便输出 DEBUG 信息
sys_logger = logging.getLogger(__name__)

class IngestionService:
    def __init__(self):
        """
        初始化加工车间
        """
        self.store_manager = VectorStoreManager()
        self.embed_model = ModelFactory.get_embedding()
        self.node_parser = ModelFactory.get_text_splitter()

    async def process_directory(self, input_dir: str):
        """
        [Heavy Lifting] 执行核心入库任务
        包含详细的性能埋点 (Profiling)
        """
        logger.info(f"🔥 [DEBUG MODE] 开始处理目录: {input_dir}")
        t0 = time.time()

        # 1. 读取文件 (IO Bound)
        logger.info("📂 [Step 1] 正在调用 SimpleDirectoryReader 读取文件...")

        try:
            # 显式指定加载器参数，防止自动探测导致的死锁
            reader = SimpleDirectoryReader(
                input_dir=input_dir,
                recursive=True,
                # 明确指定支持的后缀，防止去读 .DS_Store 或其他垃圾文件
                required_exts=[".pdf", ".md", ".txt", ".docx"],
                encoding="utf-8"
            )
            documents = reader.load_data()
        except Exception as e:
            logger.error(f"❌ [Step 1 Error] 读取文件崩溃: {e}")
            import traceback
            traceback.print_exc()
            raise e

        if not documents:
            logger.warning("⚠️ 未找到文档，跳过处理")
            return

        # 🔍 [深度诊断] 打印读取到的内容摘要
        t_io = time.time() - t0
        logger.info(f"✅ 读取完成，IO耗时 {t_io:.2f}s。共加载 {len(documents)} 个文档对象。")

        # 打印前 3 个文档的头部内容，检查是否乱码
        for i, doc in enumerate(documents[:3]):
            # 替换换行符以免日志错乱
            content_preview = doc.text[:100].replace('\n', '\\n')
            sys_logger.debug(f"📄 [Doc Preview #{i}] Filename: {doc.metadata.get('file_name')} | Len: {len(doc.text)} | Content: {content_preview}...")

        # 2. 生成节点 (CPU Bound)
        logger.info(f"🔪 [Step 2] 进入切分器: {self.node_parser.__class__.__name__}")
        t1 = time.time()

        try:
            # 这里可能会因为正则回溯导致 CPU 100% 卡死
            nodes = self.node_parser.get_nodes_from_documents(documents)
        except Exception as e:
            logger.error("❌ [Step 2 Error] 切分阶段崩溃！可能是正则死循环或特殊字符。")
            import traceback
            traceback.print_exc()
            raise e

        t_cpu = time.time() - t1
        logger.info(f"✅ 切分完成，CPU耗时 {t_cpu:.2f}s。生成 {len(nodes)} 个切片。")

        # 3. 获取存储上下文
        storage_context = self.store_manager.get_storage_context()

        # 4. 存入 DocStore
        storage_context.docstore.add_documents(nodes)

        # 5. 构建索引 (Network Bound - Embedding API)
        logger.info("🚀 [Step 3] 开始 Embedding 并写入 Qdrant...")
        t2 = time.time()

        VectorStoreIndex(
            nodes,
            storage_context=storage_context,
            embed_model=self.embed_model
        )

        t_net = time.time() - t2
        logger.success(f"🎉 全部完成！Embedding耗时 {t_net:.2f}s。")