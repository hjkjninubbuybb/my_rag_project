from llama_index.core.node_parser import SentenceSplitter

from rag.core.registry import ComponentRegistry
from rag.core.types import BaseChunker

# 覆盖中文句末标点的正则，用于 SentenceSplitter 的二级回退切分
_CHINESE_SENTENCE_REGEX = "[^,.;。？！，、；：\n]+[,.;。？！，、；：]?"


@ComponentRegistry.chunker("sentence")
class SentenceChunker(BaseChunker):
    """基于句子边界的切分策略，增强中文标点感知。"""

    def create_splitter(self, chunk_size: int, chunk_overlap: int):
        return SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            paragraph_separator="\n\n",
            secondary_chunking_regex=_CHINESE_SENTENCE_REGEX,
        )
