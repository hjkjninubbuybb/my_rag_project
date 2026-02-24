"""
基于 Markdown 层级的父子节点切分器 (sentence 策略)。

功能：
- 按标题层级切分父节点（完整语义块）
- 复用中文句子切分正则（序号保护 + 日期保护）
- 建立父子关系（NodeRelationship.PARENT）
- 返回 (parent_nodes, child_nodes) 元组供序列化
"""

from llama_index.core.node_parser import MarkdownNodeParser
from llama_index.core.schema import IndexNode, NodeRelationship
from rag_shared.core.registry import ComponentRegistry
from rag_shared.core.types import BaseChunker
import re

# 复用现有的中文句子切分正则（已完美实现）
_SENTENCE_REGEX = (
    r'(?:^|\n)#{1,6}\s+[^\n]+'  # 标题行
    r'|'
    r'^\s*[-*]\s+[^\n]+'  # 列表项 (- 或 * 开头)
    r'|'
    r'\d+[.\)）][^。！？；\n]*[。！？；]+'  # 列表项（序号保护）
    r'|'
    r'(?<!\d)[^。！？；\n]*[。！？；]+'  # 普通句子（日期保护）
)


@ComponentRegistry.chunker("sentence")
class SentenceChunker(BaseChunker):
    """
    基于 Markdown 层级的父子节点切分策略 (sentence)。

    返回值：tuple (parent_nodes, child_nodes)
    - parent_nodes: 按标题层级切分的大块
    - child_nodes: 单句，绑定到父节点
    """

    def create_splitter(self, chunk_size: int, chunk_overlap: int, **kwargs):
        return SentenceSplitter()


class SentenceSplitter:
    """层级 Markdown 切分器实现。"""

    def __init__(self):
        # 父节点切分器（按 Markdown 标题层级）
        self.parent_parser = MarkdownNodeParser()

    def get_nodes_from_documents(self, documents):
        """
        从 Documents 生成父子节点。

        Returns:
            tuple: (parent_nodes, child_nodes)
        """
        all_parent_nodes = []
        all_child_nodes = []

        for doc in documents:
            # 1. 按 Markdown 标题切分父节点
            parent_nodes = self.parent_parser.get_nodes_from_documents([doc])

            # 1.1 规范化父节点的 text 和 metadata
            for parent in parent_nodes:
                # 清理 text 中的换行符
                parent.text = parent.text.replace("\r\n", "\n").replace("\r", "")
                # 清理 header_path 中的 \r
                if "header_path" in parent.metadata:
                    parent.metadata["header_path"] = parent.metadata["header_path"].replace("\r", "")

            # 2. 对每个父节点，切分子节点并建立绑定
            for parent in parent_nodes:
                # 2.1 中文句子切分（复用完美的现有逻辑）
                sentences = self._split_sentences(parent.text)

                # 2.2 为每个句子创建子节点（IndexNode）
                for i, sent in enumerate(sentences):
                    if not sent.strip():
                        continue

                    # 规范化换行符
                    text = sent.replace("\r\n", "\n").replace("\r", "")

                    # 规范化 header_path（去除 \r）
                    header_path = parent.metadata.get("header_path", "").replace("\r", "")

                    # 创建 IndexNode（轻量级节点）
                    child_node = IndexNode(
                        text=text,
                        index_id=parent.id_,  # 指向父节点 ID
                        metadata={
                            "file_name": parent.metadata.get("file_name", ""),
                            "header_path": header_path,
                            "sentence_index": i,
                            "parent_id": parent.id_,
                        },
                    )

                    # 建立父子关系
                    child_node.relationships[NodeRelationship.PARENT] = parent.as_related_node_info()

                    all_child_nodes.append(child_node)

                all_parent_nodes.append(parent)

        return all_parent_nodes, all_child_nodes

    def _split_sentences(self, text: str) -> list[str]:
        """中文句子切分（序号保护 + 日期保护）。"""
        sentences = re.findall(_SENTENCE_REGEX, text, re.MULTILINE)
        return [s.strip() for s in sentences if s.strip()]
