"""
[Architecture Role: Model Factory (模型工厂)]
此模块负责生产 LLM 和 Embedding 模型实例。

关键架构决策:
1. [LLM] 阿里云 Qwen-Plus。
2. [Dense] 阿里云 text-embedding-v4。
3. [Sparse] BGE-M3 (集成 ModelScope 极速下载)。
"""

from typing import Dict, List, Tuple, Callable, Any
import traceback  # 👈 新增导入

# 👇 核心组件
from FlagEmbedding import BGEM3FlagModel
from llama_index.llms.dashscope import DashScope
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.postprocessor.dashscope_rerank import DashScopeRerank
from app.settings import settings

# 👇 尝试导入 ModelScope (用于国内极速下载)
try:
    from modelscope import snapshot_download
    HAS_MODELSCOPE = True
except ImportError:
    HAS_MODELSCOPE = False


class ModelFactory:
    _bgem3_cache = None

    @staticmethod
    def get_llm():
        return DashScope(
            model_name=settings.llm_model,
            api_key=settings.dashscope_api_key,
            temperature=0.1
        )

    @staticmethod
    def get_embedding():
        return OpenAIEmbedding(
            model_name=settings.embedding_model,
            api_key=settings.dashscope_api_key,
            api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            embed_batch_size=10,
        )

    @staticmethod
    def get_rerank():
        return DashScopeRerank(
            model="gte-rerank",
            api_key=settings.dashscope_api_key,
            top_n=5
        )

    @staticmethod
    def warmup_sparse_model():
        """
        [Startup Hook] 智能加载 BGE-M3
        逻辑: 优先使用 ModelScope (阿里源) 下载/加载，失败则回退到 HuggingFace。
        """
        if ModelFactory._bgem3_cache is None:
            print("⏳ [System] 正在初始化稀疏模型 (BGE-M3)...")

            # 默认路径 (如果 ModelScope 不可用，就走 HF 默认行为)
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
                # use_fp16=True 省显存
                ModelFactory._bgem3_cache = BGEM3FlagModel(model_path_or_id, use_fp16=True)
                print("✅ [System] BGE-M3 加载完成！")
            except Exception as e:
                print(f"❌ [System] BGE-M3 加载失败: {e}")
                raise e

    @staticmethod
    def get_qdrant_sparse_encoders() -> Tuple[Callable, Callable]:
        """
        [Adapter] BGE-M3 -> Qdrant 格式适配器

        Critical Fix:
        LlamaIndex 的 Qdrant 插件要求 sparse_doc_fn 返回 tuple(indices, values)，
        而不是 list[dict]。如果不拆分，会报 "too many values to unpack"。
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
                # 👇 [新增] 强力清洗与调试打印
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
                # 即使是单条查询，Qdrant 插件可能也会尝试按 batch 索引访问 [0]
                return [indices], [values]

            except Exception as e:
                # 👇 [新增] 打印堆栈以便调试
                traceback.print_exc()
                print(f"❌ [BGE-M3 Error] Query 编码出错: {e} | Query内容: '{query}'")
                return [[]], [[]]

        return sparse_doc_fn, sparse_query_fn