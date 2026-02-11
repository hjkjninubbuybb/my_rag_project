import sys
import os
import argparse
import json
from typing import List, Optional

# --- 1. 环境与路径设置 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_path = os.path.join(project_root, "src")
sys.path.append(src_path)

from qdrant_client import QdrantClient
from app.settings import settings


def probe_collection(limit: int = 5):
    print(f"🔍 [Probe] 正在连接 Qdrant...")
    print(f"   -> 路径: {settings.qdrant_path}")
    print(f"   -> 集合: {settings.collection_name}")

    if not os.path.exists(settings.qdrant_path):
        print(f"❌ [Error] Qdrant 路径不存在")
        return

    client = QdrantClient(path=settings.qdrant_path)

    # 检查集合是否存在
    collections = client.get_collections().collections
    exists = any(c.name == settings.collection_name for c in collections)

    if not exists:
        print(f"❌ [Error] 集合 '{settings.collection_name}' 不存在！")
        return

    print(f"✅ [Success] 集合存在，正在采样前 {limit} 条数据...")

    # 获取数据
    records, _ = client.scroll(
        collection_name=settings.collection_name,
        limit=limit,
        with_payload=True,
        with_vectors=False
    )

    if not records:
        print("⚠️ [Warning] 集合是空的。")
        return

    print(f"\n{'=' * 20} 数据采样 (Deep Debug) {'=' * 20}\n")
    for i, record in enumerate(records):
        print(f"📄 [Record #{i + 1}] ID: {record.id}")
        payload = record.payload

        if payload:
            # 1. 打印所有可用的 Key，看看数据藏在哪
            print(f"   🔑 Keys found: {list(payload.keys())}")

            # 2. 尝试获取元数据
            print(f"   📂 Source: {payload.get('file_name', 'N/A')}")

            # 3. [核心调试] 寻找文本内容
            # LlamaIndex 有时会把内容存在 text, 有时在 _node_content, 有时在 page_content
            content = payload.get('text')

            # 如果 text 为空，尝试解析 _node_content
            if not content and '_node_content' in payload:
                print("   ⚠️ 'text' 字段为空，尝试解析 '_node_content'...")
                try:
                    node_data = json.loads(payload['_node_content'])
                    content = node_data.get('text', '')
                    print("   ✅ 从 '_node_content' 中成功提取文本！")
                except:
                    content = "❌ 解析 _node_content 失败"

            # 打印最终提取到的内容
            if content:
                preview = content[:100].replace('\n', ' ') + "..." if len(content) > 100 else content
                print(f"   📝 Content: {preview}")
            else:
                print(f"   ❌ Content is EMPTY! Payload dump: {str(payload)[:200]}...")

        print("-" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    if args.config:
        settings.load_experiment_config(args.config)

    probe_collection(limit=args.limit)