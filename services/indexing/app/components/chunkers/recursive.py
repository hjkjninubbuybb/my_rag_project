from llama_index.core.node_parser import LangchainNodeParser
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.registry import ComponentRegistry
from app.core.types import BaseChunker

_ZH_SEPARATORS = [
    "\n\n", "\n", "。", "？", "！", "；", "，", " ", "",
]


@ComponentRegistry.chunker("recursive")
class RecursiveChunker(BaseChunker):
    """递归分隔符切分，按中文标点层级递归回退。"""

    def create_splitter(self, chunk_size: int, chunk_overlap: int, **kwargs):
        lc_splitter = RecursiveCharacterTextSplitter(
            separators=_ZH_SEPARATORS,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            keep_separator=True,
        )
        return LangchainNodeParser(lc_splitter)
