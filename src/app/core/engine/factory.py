"""
[Architecture Role: Model Factory (模型工厂)]
此模块负责生产系统所需的所有模型实例，实现了 "工厂模式" (Factory Pattern)。

核心职责:
1. [LLM & Embedding] 统一管理大模型和向量模型的初始化参数。
2. [Strategy Dispatch] 根据配置文件 (YAML) 中的策略字段，动态组装算法组件。
3. [Singleton Cache] 对重型模型 (如 BGE-M3) 进行单例缓存，避免重复加载消耗显存。

核心升级 (Phase 6 - Fix & De-bloat):
- [Fix] 修复 Embedding Batch Size 过大导致阿里云 API 报错 (400 Bad Request) 的问题。
- [Optimization] 保持纯 Python 实现的 `ChineseRecursiveTextSplitter`，无需 NLTK。
- [Pydantic] 保持正确的字段声明。
"""

from typing import Tuple, Callable, List, Any
import traceback
import re

# 👇 Pydantic 用于处理类属性
from pydantic import PrivateAttr

# 👇 LlamaIndex 核心组件
from llama_index.core.node_parser import (
    NodeParser,
    TokenTextSplitter,
    SemanticSplitterNodeParser
)
from llama_index.core.schema import TextNode
from llama_index.llms.dashscope import DashScope
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.postprocessor.dashscope_rerank import DashScopeRerank
from FlagEmbedding import BGEM3FlagModel

from app.settings import settings

try:
    from modelscope import snapshot_download
    HAS_MODELSCOPE = True
except ImportError:
    HAS_MODELSCOPE = False


# --- [Stage 1] 物理切分器 (The Atomizer) ---

# 🌟 [常量] 中文微切分正则
CHINESE_SPLIT_REGEX = r'[^。！？，；]+[。！？，；]?'

def chinese_sentence_splitter(text: str) -> List[str]:
    """[函数版] 供 SemanticSplitter 使用"""
    pattern = re.compile(CHINESE_SPLIT_REGEX)
    segments = [s.strip() for s in pattern.findall(text) if s.strip()]
    return [s for s in segments if len(s) > 1]


# 🌟 [Class版] 纯 Python 实现的递归切分器 (替代 SentenceSplitter)
class ChineseRecursiveTextSplitter(NodeParser):
    """
    [No-NLTK Splitter]
    专门为中文设计的递归切分器，不依赖 nltk，不联网。
    """

    # ✅ Pydantic 字段声明
    chunk_size: int
    chunk_overlap: int

    # 私有属性
    _pattern: Any = PrivateAttr()

    def __init__(self, chunk_size: int, chunk_overlap: int, **kwargs):
        super().__init__(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            **kwargs
        )
        self._pattern = re.compile(CHINESE_SPLIT_REGEX)

    def _parse_nodes(self, documents, show_progress=False, **kwargs):
        all_nodes = []
        for doc in documents:
            text = doc.text
            if not text: continue

            # 1. 打散 (Atomize)
            segments = [s for s in self._pattern.findall(text) if s.strip()]

            # 2. 合并 (Merge with Overlap)
            current_chunk_segs = []
            current_len = 0

            for seg in segments:
                seg_len = len(seg)

                # 如果加上这一段会爆掉 chunk_size，就先结算当前块
                if current_len + seg_len > self.chunk_size and current_chunk_segs:
                    # 生成文本块
                    chunk_text = "".join(current_chunk_segs)
                    all_nodes.append(TextNode(text=chunk_text, metadata=doc.metadata))

                    # [Overlap Logic] 处理重叠窗口
                    backtrack_segs = []
                    backtrack_len = 0
                    for prev_seg in reversed(current_chunk_segs):
                        if backtrack_len + len(prev_seg) < self.chunk_overlap:
                            backtrack_segs.insert(0, prev_seg)
                            backtrack_len += len(prev_seg)
                        else:
                            break

                    # 重置当前块
                    current_chunk_segs = backtrack_segs
                    current_len = backtrack_len

                # 加入当前段
                current_chunk_segs.append(seg)
                current_len += seg_len

            # 处理剩余的尾巴
            if current_chunk_segs:
                chunk_text = "".join(current_chunk_segs)
                all_nodes.append(TextNode(text=chunk_text, metadata=doc.metadata))

        return all_nodes


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
        """
        获取 Dense Embedding (稠密向量) 模型
        """
        return OpenAIEmbedding(
            model_name=settings.embedding_model,
            api_key=settings.dashscope_api_key,
            api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            # 🔴 [FIX] 阿里云 API 硬限制：Batch Size 不能超过 10
            # 之前设为 100 导致了 400 Bad Request
            embed_batch_size=10,
        )

    @staticmethod
    def get_rerank():
        return DashScopeRerank(
            model="gte-rerank",
            api_key=settings.dashscope_api_key,
            top_n=settings.rerank_top_k
        )

    @staticmethod
    def get_text_splitter() -> NodeParser:
        """
        [Factory Method] 文本切分器工厂
        """
        strategy = settings.chunking_strategy
        size = settings.chunk_size_child
        overlap = settings.chunk_overlap

        print(f"🏭 [Factory] 正在构建切片器 | 策略: {strategy}")

        if strategy == "fixed":
            # 策略 A: 纯机械切分
            return TokenTextSplitter(
                chunk_size=size,
                chunk_overlap=overlap,
                separator=""
            )

        elif strategy in ["recursive", "sentence"]:
            # 策略 B: 增强型句子切分 (使用自定义类)
            print(f"   -> [Stage 1] 启用中文微切分 (No-NLTK Custom Class)")
            print(f"   -> [Stage 2] 合并大小: {size}")

            return ChineseRecursiveTextSplitter(
                chunk_size=size,
                chunk_overlap=overlap
            )

        elif strategy == "semantic":
            # 策略 C: 语义分割
            print(f"   -> [Stage 1] 启用中文微切分 (Function模式)")
            print(f"   -> [Stage 2] 初始化语义聚类")

            embed_model = ModelFactory.get_embedding()
            buffer_size = settings.semantic_buffer_size
            threshold = settings.semantic_breakpoint_threshold

            return SemanticSplitterNodeParser(
                buffer_size=buffer_size,
                breakpoint_percentile_threshold=threshold,
                embed_model=embed_model,
                sentence_splitter=chinese_sentence_splitter
            )

        else:
            print(f"⚠️ [Factory Warning] 未知策略 '{strategy}'，回退到 TokenTextSplitter")
            return TokenTextSplitter(chunk_size=size, chunk_overlap=overlap)

    @staticmethod
    def warmup_sparse_model():
        if ModelFactory._bgem3_cache is None:
            print("⏳ [System] 正在初始化稀疏模型 (BGE-M3)...")
            model_path_or_id = "BAAI/bge-m3"

            if HAS_MODELSCOPE:
                try:
                    print("🚀 [Downloader] 正在通过阿里云极速通道获取模型...")
                    model_path_or_id = snapshot_download(
                        'Xorbits/bge-m3',
                        cache_dir='./resources',
                        revision='master'
                    )
                except Exception as e:
                    print(f"⚠️ [Downloader] ModelScope 下载异常: {e}")
            else:
                print("⚠️ [Downloader] 未安装 modelscope，将使用默认源...")

            try:
                ModelFactory._bgem3_cache = BGEM3FlagModel(model_path_or_id, use_fp16=True)
                print("✅ [System] BGE-M3 加载完成！")
            except Exception as e:
                print(f"❌ [System] BGE-M3 加载失败: {e}")
                raise e

    @staticmethod
    def get_qdrant_sparse_encoders() -> Tuple[Callable, Callable]:
        if ModelFactory._bgem3_cache is None:
            ModelFactory.warmup_sparse_model()
        model = ModelFactory._bgem3_cache

        def sparse_doc_fn(texts: List[str]) -> Tuple[List[List[int]], List[List[float]]]:
            try:
                output = model.encode(texts, return_dense=False, return_sparse=True, return_colbert_vecs=False)
                batch_indices = []
                batch_values = []
                for item in output['lexical_weights']:
                    indices = []
                    values = []
                    for k, v in item.items():
                        indices.append(int(k))
                        values.append(float(v))
                    batch_indices.append(indices)
                    batch_values.append(values)
                return batch_indices, batch_values
            except Exception as e:
                print(f"❌ [BGE-M3 Error] 稀疏向量计算出错: {e}")
                return [[] for _ in texts], [[] for _ in texts]

        def sparse_query_fn(query: str) -> Tuple[List[int], List[float]]:
            try:
                if not isinstance(query, str): query = str(query)
                query = query.strip()
                if not query: return [[]], [[]]
                output = model.encode([query], return_dense=False, return_sparse=True, return_colbert_vecs=False)
                item = output['lexical_weights'][0]
                indices = []
                values = []
                for k, v in item.items():
                    indices.append(int(k))
                    values.append(float(v))
                return [indices], [values]
            except Exception as e:
                traceback.print_exc()
                print(f"❌ [BGE-M3 Error] Query 编码出错: {e}")
                return [[]], [[]]

        return sparse_doc_fn, sparse_query_fn