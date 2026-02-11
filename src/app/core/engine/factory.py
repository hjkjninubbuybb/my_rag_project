"""
[Architecture Role: Model Factory (模型工厂)]
此模块负责生产系统所需的所有模型实例，实现了 "工厂模式" (Factory Pattern)。

核心职责:
1. [LLM & Embedding] 统一管理大模型和向量模型的初始化参数。
2. [Strategy Dispatch] 根据配置文件 (YAML) 中的策略字段，动态组装算法组件。
3. [Singleton Cache] 对重型模型 (如 BGE-M3) 进行单例缓存，避免重复加载消耗显存。

核心升级 (Phase 4):
- 新增 `get_text_splitter()` 方法，实现了文本切分算法的策略路由 (Routing)。
- 支持 "Fixed Token" (基准) 与 "Recursive Character" (语义增强) 两种策略的无缝切换。
"""

from typing import Tuple, Callable, List, Any
import traceback

# 👇 LlamaIndex 核心组件
# NodeParser 是所有切分器的基类 (Base Class)，用于类型提示
from llama_index.core.node_parser import NodeParser, TokenTextSplitter, SentenceSplitter
from llama_index.llms.dashscope import DashScope
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.postprocessor.dashscope_rerank import DashScopeRerank
from FlagEmbedding import BGEM3FlagModel

from app.settings import settings

# 👇 尝试导入 ModelScope (用于国内极速下载)
try:
    from modelscope import snapshot_download
    HAS_MODELSCOPE = True
except ImportError:
    HAS_MODELSCOPE = False


class ModelFactory:
    # BGE-M3 模型缓存 (单例模式，防止多次加载爆内存)
    _bgem3_cache = None

    @staticmethod
    def get_llm():
        """
        获取 LLM (大语言模型) 实例
        当前配置: 阿里云 Qwen-Plus
        """
        return DashScope(
            model_name=settings.llm_model,
            api_key=settings.dashscope_api_key,
            temperature=0.1  # 保持低温度以获得稳定的事实性回答
        )

    @staticmethod
    def get_embedding():
        """
        获取 Dense Embedding (稠密向量) 模型
        当前配置: 阿里云 text-embedding-v4 (1536维)
        实现: 使用 OpenAI 兼容接口调用 DashScope
        """
        return OpenAIEmbedding(
            model_name=settings.embedding_model,
            api_key=settings.dashscope_api_key,
            api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            embed_batch_size=10,
        )

    @staticmethod
    def get_rerank():
        """
        获取 Reranker (重排序) 模型
        作用: 对检索回来的 Top-K 文档进行二次精排，提升准确率。
        """
        return DashScopeRerank(
            model="gte-rerank",
            api_key=settings.dashscope_api_key,
            top_n=settings.rerank_top_k  # 动态读取 YAML 配置
        )

    @staticmethod
    def get_text_splitter() -> NodeParser:
        """
        [Factory Method] 文本切分器工厂

        设计意图 (Thesis Point):
        实现了算法策略的解耦。根据配置文件中的 `chunking_strategy` 字段，
        动态返回不同的切分器实例，支持消融实验 (Ablation Study)。

        策略说明:
        1. strategy="fixed" -> TokenTextSplitter
           - 原理: 按固定的 Token 数量强制切断。
           - 优点: 保证每个块的大小一致，计算效率高。
           - 缺点: 容易在句子中间切断，导致语义不完整。
           - 场景: 作为 Baseline (基准) 对照组。

        2. strategy="recursive" / "sentence" -> SentenceSplitter
           - 原理: 递归地寻找分隔符 (如句号、换行)，优先保持句子完整性。
           - 优点: 语义连贯性强，利于 LLM 理解上下文。
           - 缺点: 块大小会有波动。
           - 场景: 实验组 (Proposed Method)。
        """
        strategy = settings.chunking_strategy
        size = settings.chunk_size_child
        overlap = settings.chunk_overlap

        print(f"🏭 [Factory] 正在构建切片器 | 策略: {strategy} | 大小: {size} | 重叠: {overlap}")

        if strategy == "fixed":
            # 策略 A: 固定 Token 切片
            return TokenTextSplitter(
                chunk_size=size,
                chunk_overlap=overlap,
                separator=" "  # 硬切分时的分隔符
            )

        elif strategy in ["recursive", "sentence"]:
            # 策略 B: 递归/句子切片 (LlamaIndex 默认推荐)
            return SentenceSplitter(
                chunk_size=size,
                chunk_overlap=overlap,
                # SentenceSplitter 内部会自动处理中文标点 (如 "。", "！")
            )

        else:
            # 防御性回退 (Defensive Coding)
            # 虽然 Settings 已经做了校验，但工厂层仍需处理意外情况
            print(f"⚠️ [Factory Warning] 未知策略 '{strategy}'，系统将回退到默认的 TokenTextSplitter")
            return TokenTextSplitter(chunk_size=size, chunk_overlap=overlap)

    @staticmethod
    def warmup_sparse_model():
        """
        [Startup Hook] 智能加载 BGE-M3 稀疏向量模型

        逻辑:
        1. 检查单例缓存，如果已加载直接跳过。
        2. 优先使用 ModelScope (阿里源) 下载，解决国内 HuggingFace 连接困难的问题。
        3. 如果 ModelScope 不可用，回退到 HuggingFace 默认行为。
        """
        if ModelFactory._bgem3_cache is None:
            print("⏳ [System] 正在初始化稀疏模型 (BGE-M3)...")
            # 默认 ID
            model_path_or_id = "BAAI/bge-m3"

            # 👇 核心集成：自动从阿里云下载
            if HAS_MODELSCOPE:
                try:
                    print("🚀 [Downloader] 检测到 modelscope，正在通过阿里云极速通道获取模型...")
                    # cache_dir 指定下载到项目的 resources 目录，方便管理
                    # Xorbits/bge-m3 是 BAAI/bge-m3 的官方镜像
                    model_path_or_id = snapshot_download(
                        'Xorbits/bge-m3',
                        cache_dir='./resources',
                        revision='master'
                    )
                    print(f"✅ [Downloader] 模型就绪，路径: {model_path_or_id}")
                except Exception as e:
                    print(f"⚠️ [Downloader] ModelScope 下载异常 (将尝试官方源): {e}")
            else:
                print("⚠️ [Downloader] 未安装 modelscope，将使用默认源 (可能较慢)...")

            # 加载模型
            try:
                # use_fp16=True 省显存 (Half Precision)
                ModelFactory._bgem3_cache = BGEM3FlagModel(model_path_or_id, use_fp16=True)
                print("✅ [System] BGE-M3 加载完成！")
            except Exception as e:
                print(f"❌ [System] BGE-M3 加载失败: {e}")
                raise e

    @staticmethod
    def get_qdrant_sparse_encoders() -> Tuple[Callable, Callable]:
        """
        [Adapter] BGE-M3 -> Qdrant 格式适配器

        Critical Fix (核心修复):
        LlamaIndex 的 Qdrant 插件要求 sparse_doc_fn 返回 tuple(indices, values)，
        而不是 list[dict]。如果不拆分，会报 "too many values to unpack"。
        此适配器负责将 FlagEmbedding 的输出格式转换为 QdrantClient 要求的格式。
        """
        if ModelFactory._bgem3_cache is None:
            ModelFactory.warmup_sparse_model()

        model = ModelFactory._bgem3_cache

        def sparse_doc_fn(texts: List[str]) -> Tuple[List[List[int]], List[List[float]]]:
            """
            文档编码器：将文本列表转换为 (indices_list, values_list)
            """
            try:
                # 1. 调用模型计算 (batch)
                output = model.encode(texts, return_dense=False, return_sparse=True, return_colbert_vecs=False)

                batch_indices = []
                batch_values = []

                # 2. 遍历结果，拆分为索引和权重两个独立列表
                for item in output['lexical_weights']:
                    # item 是 {str(token_id): float(weight)}
                    indices = []
                    values = []
                    for k, v in item.items():
                        indices.append(int(k))
                        values.append(float(v))

                    batch_indices.append(indices)
                    batch_values.append(values)

                # 👇 返回两个列表的元组，这就只有 2 个值了，满足 unpacking
                return batch_indices, batch_values

            except Exception as e:
                print(f"❌ [BGE-M3 Error] 稀疏向量计算出错: {e}")
                # 出错时返回空列表元组，防止崩溃
                return [[] for _ in texts], [[] for _ in texts]

        def sparse_query_fn(query: str) -> Tuple[List[int], List[float]]:
            """
            查询编码器：将单条查询转换为 (indices, values)
            """
            try:
                # 👇 强力清洗与调试打印
                if not isinstance(query, str):
                    query = str(query)
                query = query.strip()

                # 如果是空字符串，直接返回空向量（必须是列表的列表格式）
                if not query:
                    print(f"⚠️ [BGE-M3 Warning] 跳过空查询")
                    return [[]], [[]]

                output = model.encode([query], return_dense=False, return_sparse=True, return_colbert_vecs=False)
                item = output['lexical_weights'][0]

                indices = []
                values = []
                for k, v in item.items():
                    indices.append(int(k))
                    values.append(float(v))

                # Qdrant Query 接口也要求解包为 2 个值
                # 👇【核心修改】这里必须包一层 []，变成 List[List]
                return [indices], [values]

            except Exception as e:
                # 👇 打印堆栈以便调试
                traceback.print_exc()
                print(f"❌ [BGE-M3 Error] Query 编码出错: {e} | Query内容: '{query}'")
                return [[]], [[]]

        return sparse_doc_fn, sparse_query_fn