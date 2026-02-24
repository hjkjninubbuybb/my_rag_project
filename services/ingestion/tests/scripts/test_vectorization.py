"""
向量化和 DocStore 测试脚本 - 测试完整的 ingestion 流程

输入: services/ingestion/tests/datas/cleaner_test_results/policy/
测试: 向量化 + DocStore 存储

注意: 需要先启动 Qdrant (docker run -p 6333:6333 qdrant/qdrant)
或使用本地路径模式
"""

import sys
import os
import asyncio
import json
from pathlib import Path

# 读取 .env 文件
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# 设置 UTF-8 编码
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from llama_index.core import SimpleDirectoryReader

from rag_shared.core.registry import ComponentRegistry
from rag_shared.config.experiment import ExperimentConfig

from app.services.ingestion import IngestionService


def main():
    # 导入 chunkers 和 providers 以注册组件
    import app.components.chunkers  # noqa: F401
    import app.components.providers  # noqa: F401

    # 输入目录: 清洗后的 markdown 文件
    input_dir = Path(__file__).parent.parent / "datas" / "cleaner_test_results" / "policy"

    # 测试配置 - 使用本地 Qdrant 路径
    config = ExperimentConfig(
        qdrant_url="http://localhost:6333",
        collection_name_override="test_sentence_policy",
        chunking_strategy="sentence",
        chunk_size_parent=1000,
        chunk_size_child=200,
        chunk_overlap=50,
        embedding_provider="dashscope",
        embedding_model="text-embedding-v4",
        enable_hybrid=False,
        dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", ""),
    )

    # 获取所有测试文件
    md_files = list(input_dir.glob("*.md"))
    if not md_files:
        print(f"未找到测试文件: {input_dir}")
        return

    print(f"找到 {len(md_files)} 个测试文件")

    # 运行 ingestion - 处理所有文件
    async def run_test():
        service = IngestionService(config)
        result = await service.process_files([str(f) for f in md_files])
        return result

    result = asyncio.run(run_test())

    print("\n" + "="*50)
    print("测试结果:")
    print(f"  父节点数量: {result.get('parent_count', 0)}")
    print(f"  子节点数量: {result.get('child_count', 0)}")
    print(f"  向量化数量: {result.get('vectorized_count', 0)}")
    print(f"  Collection: {result.get('collection_name', '')}")
    print("="*50)

    # 检查 docstore 文件
    docstore_path = Path("D:/Projects/my_rag_project/data/vectordb")
    if docstore_path.exists():
        print(f"\nDocStore 文件位置: {docstore_path}")
        for f in docstore_path.glob("test_sentence_policy*"):
            print(f"  - {f.name}")
            if f.suffix == ".json":
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    print(f"    内容预览: {str(data)[:200]}...")


if __name__ == "__main__":
    main()
