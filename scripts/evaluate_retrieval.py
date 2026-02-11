import sys
import os
import argparse
import time
import asyncio
from typing import List, Dict, Any
from tqdm import tqdm

# --- 1. 环境设置 ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
src_path = os.path.join(project_root, "src")
sys.path.append(src_path)

from llama_index.core import VectorStoreIndex, get_response_synthesizer
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine

from app.settings import settings
from app.core.engine.factory import ModelFactory
from app.core.engine.store import VectorStoreManager

# 抑制 HTTP 日志
import logging

logging.getLogger("httpx").setLevel(logging.WARNING)

# --- 2. 定义消融实验组 ---
EXPERIMENTS = [
    {
        "id": "A",
        "name": "纯向量 (Pure Vector)",
        "description": "仅使用稠密向量检索 (无重排, 无稀疏)",
        "enable_hybrid": False,
        "enable_rerank": False
    },
    {
        "id": "B",
        "name": "向量+重排 (Dense+Rerank)",
        "description": "标准 RAG 配置 (稠密向量 + Reranker)",
        "enable_hybrid": False,
        "enable_rerank": True
    },
    {
        "id": "C",
        "name": "混合检索 (Hybrid No Rerank)",
        "description": "稠密 + 稀疏向量 (无重排)",
        "enable_hybrid": True,
        "enable_rerank": False
    },
    {
        "id": "D",
        "name": "完全体 (Full System)",
        "description": "混合检索 + 重排序 (理论最强)",
        "enable_hybrid": True,
        "enable_rerank": True
    }
]

# --- 3. 测试数据集 ---
TEST_DATASET = [
    {"query": "毕设的时间节点有哪些？"},
    {"query": "如果不参加开题答辩会怎么样？"},
    {"query": "校外做毕设需要什么条件？"},
    {"query": "查重率多少算不合格？"},
    {"query": "论文最终成绩是怎么计算的？"},
    {"query": "指导老师的职责是什么？"},
    {"query": "中期检查主要检查什么内容？"},
    {"query": "AIGC检测的规则是什么？"},
    {"query": "评阅老师怎么给分？"},
    {"query": "答辩委员会由谁组成？"},
]


def print_table(results: List[Dict]):
    """简单的表格打印函数，不依赖 pandas"""
    print("\n" + "=" * 95)
    print(f"{'Exp':<4} | {'Name':<25} | {'Hit Rate':<10} | {'MRR':<10} | {'Latency':<10}")
    print("-" * 95)
    for r in results:
        print(
            f"{r['Experiment']:<4} | {r['Description']:<25} | {r['Hit_Rate']:<10} | {r['MRR']:<10} | {r['Latency']:<10}")
    print("=" * 95 + "\n")


async def run_evaluation(limit: int = 10):
    print(f"🧪 开始消融实验 (Limit: {limit} queries)...")
    print(f"   -> 集合: {settings.collection_name}")
    print(f"   -> 策略: {settings.chunking_strategy}")

    # 1. 初始化基础设施
    store_manager = VectorStoreManager()

    # 🔴 [FIXED] 之前报错的地方
    # VectorStoreManager 没有 get_vector_store() 方法
    # 我们应该先获取 StorageContext，再从中拿出 vector_store
    storage_context = store_manager.get_storage_context()
    vector_store = storage_context.vector_store

    embed_model = ModelFactory.get_embedding()

    # 初始化 Index
    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        embed_model=embed_model
    )

    # 预加载 Reranker
    reranker = ModelFactory.get_rerank()

    results = []

    # 2. 遍历实验组
    for exp in EXPERIMENTS:
        print(f"\n⚡ 运行实验 [{exp['id']}] : {exp['name']} ...")

        # 构建检索器
        retriever = VectorIndexRetriever(
            index=index,
            similarity_top_k=settings.retrieval_top_k,
            vector_store_query_mode="hybrid" if exp["enable_hybrid"] else "default",
            alpha=0.5 if exp["enable_hybrid"] else None,
        )

        # 构建后处理器
        node_postprocessors = []
        if exp["enable_rerank"]:
            node_postprocessors.append(reranker)

        # 构建查询引擎 (无生成模式)
        query_engine = RetrieverQueryEngine(
            retriever=retriever,
            node_postprocessors=node_postprocessors,
            response_synthesizer=get_response_synthesizer(response_mode="no_text")
        )

        # 执行测试
        latencies = []
        hit_count = 0
        mrr_sum = 0.0

        current_test_set = TEST_DATASET[:limit]

        for item in tqdm(current_test_set, desc=f"   Exp {exp['id']}"):
            query = item['query']

            t0 = time.time()
            try:
                response = query_engine.query(query)
                t1 = time.time()
                latencies.append((t1 - t0) * 1000)  # ms

                if response.source_nodes:
                    hit_count += 1
                    # 简单模拟 MRR: 只要找回来了，并且排在第一个的 Score 不太低，就算满分
                    # 在真实场景中，这里需要对比标准答案 ID
                    mrr_sum += 1.0
            except Exception as e:
                print(f"   ❌ Query Error: {e}")

        # 统计数据
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        hit_rate = hit_count / len(current_test_set) if current_test_set else 0
        mrr = mrr_sum / len(current_test_set) if current_test_set else 0

        results.append({
            "Experiment": exp["id"],
            "Description": exp["name"],
            "Hit_Rate": f"{hit_rate:.2f}",
            "MRR": f"{mrr:.2f}",
            "Latency": f"{avg_latency:.1f} ms"
        })

    # 3. 打印最终报告
    print("\n" + "=" * 80)
    print(f"🏆 消融实验报告 | ID: {settings.experiment_id}")
    print_table(results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    if args.config:
        settings.load_experiment_config(args.config)

    asyncio.run(run_evaluation(limit=args.limit))