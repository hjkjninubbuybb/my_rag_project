from llama_index.core.node_parser import TokenTextSplitter

from app.core.registry import ComponentRegistry
from app.core.types import BaseChunker


@ComponentRegistry.chunker("fixed")
class FixedChunker(BaseChunker):
    """固定 Token 长度切分 (基准方案)。"""

    def create_splitter(self, chunk_size: int, chunk_overlap: int, **kwargs):
        return TokenTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separator=" ",
        )
