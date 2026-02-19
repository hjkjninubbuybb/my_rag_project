from llama_index.core.node_parser import LangchainNodeParser
from langchain_text_splitters import RecursiveCharacterTextSplitter

from rag.core.registry import ComponentRegistry
from rag.core.types import BaseChunker

# 中文分隔符层级：段落 → 换行 → 句号 → 问号 → 感叹号 → 分号 → 逗号 → 空格 → 逐字符
_ZH_SEPARATORS = [
    "\n\n",
    "\n",
    "。",
    "？",
    "！",
    "；",
    "，",
    " ",
    "",
]


@ComponentRegistry.chunker("recursive")
class RecursiveChunker(BaseChunker):
    """递归分隔符切分，按中文标点层级递归回退。"""

    def create_splitter(self, chunk_size: int, chunk_overlap: int):
        lc_splitter = RecursiveCharacterTextSplitter(
            separators=_ZH_SEPARATORS,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            keep_separator=True,
        )
        return LangchainNodeParser(lc_splitter)
