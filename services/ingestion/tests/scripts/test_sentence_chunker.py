"""
切片模块测试脚本 - 测试新的 sentence 策略
输入: services/ingestion/tests/datas/cleaner_test_results/policy/
输出: services/ingestion/tests/datas/sentence_chunker_test_results/policy/
"""

import sys
import json
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from llama_index.core import SimpleDirectoryReader

from rag_shared.core.registry import ComponentRegistry


def main():
    # 导入 chunkers 以注册组件
    import app.components.chunkers  # noqa: F401

    # 输入目录: 清洗后的 markdown 文件
    input_dir = Path(__file__).parent.parent / "datas" / "cleaner_test_results" / "policy"

    # 输出目录: 切片结果
    output_dir = Path(__file__).parent.parent / "datas" / "sentence_chunker_test_results" / "policy"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        return

    # 获取所有 markdown 文件
    md_files = list(input_dir.glob("*.md"))
    if not md_files:
        return

    # 获取 sentence chunker
    chunker = ComponentRegistry.get_chunker("sentence")
    node_parser = chunker.create_splitter(chunk_size=500, chunk_overlap=50)

    for md_file in md_files:
        # 读取文档
        documents = SimpleDirectoryReader(input_files=[str(md_file)]).load_data()

        # 切片
        parent_nodes, child_nodes = node_parser.get_nodes_from_documents(documents)

        # 保存父节点
        parents_data = []
        for node in parent_nodes:
            parents_data.append({
                "id": node.id_,
                "text": node.text[:200] + "..." if len(node.text) > 200 else node.text,
                "metadata": node.metadata,
            })

        # 保存子节点
        children_data = []
        for node in child_nodes:
            children_data.append({
                "id": node.id_,
                "text": node.text[:100] + "..." if len(node.text) > 100 else node.text,
                "metadata": node.metadata,
                "parent_id": node.metadata.get("parent_id", ""),
            })

        # 输出父节点
        parents_file = output_dir / f"{md_file.stem}_parents.json"
        with open(parents_file, "w", encoding="utf-8") as f:
            json.dump({
                "file": md_file.name,
                "count": len(parent_nodes),
                "parents": parents_data,
            }, f, ensure_ascii=False, indent=2)

        # 输出子节点
        children_file = output_dir / f"{md_file.stem}_children.json"
        with open(children_file, "w", encoding="utf-8") as f:
            json.dump({
                "file": md_file.name,
                "count": len(child_nodes),
                "children": children_data,
            }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
