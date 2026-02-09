import sys
import os
import json
from qdrant_client import QdrantClient

# 1. 强行把 src 目录加入 Python 搜索路径，防止找不到模块
current_dir = os.getcwd()
src_path = os.path.join(current_dir, "src")
if src_path not in sys.path:
    sys.path.append(src_path)

# 2. 导入配置
try:
    from app.settings import settings
except ImportError as e:
    print("❌ 无法导入 settings，请确保你在项目根目录下运行此脚本。")
    print(f"   错误详情: {e}")
    sys.exit(1)


def probe():
    print("-" * 50)
    print("🕵️‍♂️ [Qdrant 探针] 开始工作...")
    print(f"📂 数据库路径: {settings.qdrant_path}")

    # 3. 连接数据库
    if not os.path.exists(settings.qdrant_path):
        print("❌ 错误: 数据库文件夹不存在！你确定运行过 Ingest 吗？")
        return

    client = QdrantClient(path=settings.qdrant_path)
    collection_name = "my_rag_collection"

    # 4. 检查集合
    if not client.collection_exists(collection_name):
        print(f"❌ 错误: 集合 '{collection_name}' 不存在！")
        return

    # 5. 抓取第 1 条数据 (Limit=1)
    print(f"✅ 集合存在，正在提取第 1 条样本数据...")
    records, _ = client.scroll(
        collection_name=collection_name,
        limit=1,
        with_payload=True,  # 必须拿 Payload，这才是存元数据的地方
        with_vectors=False  # 向量数据是一堆乱码数字，不需要看
    )

    if not records:
        print("⚠️ 警告: 集合是空的 (Empty)！")
        print("   -> 这意味着之前的 Ingest 虽然显示成功，但其实没写进去数据。")
        return

    # 6. 打印真相
    point = records[0]
    payload = point.payload

    print("\n🔍 [真相大白] 数据库里存的数据结构如下：")
    print("=" * 50)
    # 使用 json.dumps 格式化打印，方便阅读
    print(json.dumps(payload, indent=4, ensure_ascii=False))
    print("=" * 50)

    print("\n👉 请把上面 '=' 之间的 JSON 内容截图或复制发给我！")


if __name__ == "__main__":
    probe()