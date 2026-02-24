"""语义切片策略 — 基于 Embedding 余弦相似度的自适应分割。"""

import re
from typing import List

from llama_index.core.node_parser import SemanticSplitterNodeParser

from rag_shared.core.registry import ComponentRegistry
from rag_shared.core.types import BaseChunker
from rag_shared.utils.logger import logger

_SENTENCE_PATTERN = re.compile(r"[^.?!;。？！；\n]+[.?!;。？！；]?")


def _sentence_splitter(text: str) -> List[str]:
    """中英文混合分句器，供 SemanticSplitterNodeParser 使用。"""
    sentences: List[str] = []
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        matches = _SENTENCE_PATTERN.findall(paragraph)
        if matches:
            sentences.extend(s.strip() for s in matches if s.strip())
        else:
            sentences.append(paragraph)
    return sentences if sentences else [text]


@ComponentRegistry.chunker("semantic")
class SemanticChunker(BaseChunker):
    """基于语义相似度的自适应切分。

    必需 kwargs: embed_model
    可选 kwargs: breakpoint_percentile_threshold (default 95), buffer_size (default 1)
    """

    def create_splitter(self, chunk_size: int, chunk_overlap: int, **kwargs):
        embed_model = kwargs.get("embed_model")
        if embed_model is None:
            raise ValueError(
                "SemanticChunker 需要 embed_model 参数，"
                "请确保 IngestionService 正确传递了 embed_model。"
            )

        threshold = kwargs.get("breakpoint_percentile_threshold", 95)
        buffer_size = kwargs.get("buffer_size", 1)

        logger.info(
            f"语义切片: threshold={threshold}, buffer_size={buffer_size} "
            f"(chunk_size/overlap 不适用于语义切分，已忽略)"
        )

        return SemanticSplitterNodeParser(
            embed_model=embed_model,
            breakpoint_percentile_threshold=threshold,
            buffer_size=buffer_size,
            sentence_splitter=_sentence_splitter,
        )
