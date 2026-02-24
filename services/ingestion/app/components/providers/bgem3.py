"""
轻量稀疏向量生成器（jieba 分词 + 哈希映射）。

替代原 BGE-M3（~2GB 神经网络模型），使用 jieba 中文分词生成 BM25 风格的稀疏向量。
"""

import math
import hashlib
from collections import Counter
from typing import Tuple, Callable, List

import jieba

_STOPWORDS = frozenset({
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
    "自己", "这", "他", "她", "它", "们", "那", "被", "从", "把", "对", "与", "之",
    "而", "以", "但", "为", "所", "能", "其", "如", "已", "下", "中", "来", "又",
    "或", "等", "做", "还", "可以", "这个", "那个", "什么", "怎么", "因为", "所以",
})


def _tokenize(text: str) -> List[str]:
    tokens = jieba.cut(text)
    return [
        t for t in tokens
        if len(t) >= 2 and t not in _STOPWORDS and not t.isdigit() and t.strip()
    ]


def _token_to_index(token: str) -> int:
    h = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


class SparseModelManager:
    """轻量稀疏向量管理器（jieba 分词 + 哈希稀疏向量）。"""

    _initialized = False

    @staticmethod
    def warmup():
        if SparseModelManager._initialized:
            return
        jieba.initialize()
        SparseModelManager._initialized = True

    @staticmethod
    def get_sparse_encoders() -> Tuple[Callable, Callable]:
        if not SparseModelManager._initialized:
            SparseModelManager.warmup()

        def sparse_doc_fn(texts: List[str]) -> Tuple[List[List[int]], List[List[float]]]:
            batch_indices, batch_values = [], []
            for text in texts:
                counter = Counter(_tokenize(text))
                indices = [_token_to_index(t) for t in counter]
                values = [1.0 + math.log(c) for c in counter.values()]
                batch_indices.append(indices)
                batch_values.append(values)
            return batch_indices, batch_values

        def sparse_query_fn(query: str) -> Tuple[List[int], List[float]]:
            if not isinstance(query, str):
                query = str(query)
            query = query.strip()
            if not query:
                return [[]], [[]]
            counter = Counter(_tokenize(query))
            indices = [_token_to_index(t) for t in counter]
            values = [1.0 + math.log(c) for c in counter.values()]
            return [indices], [values]

        return sparse_doc_fn, sparse_query_fn
