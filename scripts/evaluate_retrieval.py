import sys
import os
import time
import numpy as np
import pandas as pd
import argparse
from datetime import datetime  # 👈 [新增] 用于生成时间戳
from pathlib import Path
from tqdm import tqdm
from typing import List, Dict, Tuple
from dotenv import load_dotenv

# --- 1. 环境初始化 ---

current_file_path = Path(__file__).resolve()
project_root = current_file_path.parent.parent
sys.path.insert(0, str(project_root))

env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    print(f"⚠️ 警告: 未找到 .env 文件")

from app.core.engine.retrieval import RetrievalService
from app.core.engine.factory import ModelFactory
from app.settings import settings
from llama_index.core.schema import QueryBundle

# 强制修正 Qdrant 路径 (如果你修改了 .env 里的路径，请注释掉下面 3 行)
qdrant_abs_path = project_root / "qdrant_db"
if hasattr(settings, "qdrant_path"):
    settings.qdrant_path = str(qdrant_abs_path)


# --- 2. 数学工具 ---

def calculate_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return np.dot(v1, v2) / (norm1 * norm2)


def calculate_ndcg(k: int, relevance_scores: List[int]) -> float:
    scores = relevance_scores[:k]
    dcg = 0.0
    for i, rel in enumerate(scores):
        if rel > 0:
            dcg += rel / np.log2(i + 2)
    ideal_scores = sorted(scores, reverse=True)
    idcg = 0.0
    for i, rel in enumerate(ideal_scores):
        if rel > 0:
            idcg += rel / np.log2(i + 2)
    if idcg == 0:
        return 0.0
    return dcg / idcg


# --- 3. 裁判类 ---

class SemanticJudge:
    def __init__(self):
        print("⚖️ 初始化语义裁判...")
        self.embed_model = ModelFactory.get_embedding()
        self._cache = {}

    def get_embedding(self, text: str) -> List[float]:
        if text in self._cache:
            return self._cache[text]
        emb = self.embed_model.get_text_embedding(text)
        self._cache[text] = emb
        return emb

    def is_hit(self, ground_truth: str, retrieved_text: str, threshold: float = 0.85) -> bool:
        def clean(t):
            return str(t).replace(" ", "").replace("\n", "").lower()

        if clean(ground_truth) in clean(retrieved_text):
            return True
        try:
            vec_gt = self.get_embedding(ground_truth)
            vec_ret = self.get_embedding(retrieved_text)
            return calculate_cosine_similarity(vec_gt, vec_ret) > threshold
        except:
            return False


# --- 4. 实验控制器 ---

class ExperimentRunner:
    def __init__(self):
        self.service = RetrievalService()
        self.judge = SemanticJudge()
        self.reranker = self.service.reranker

        self.configs = [
            {"name": "A", "desc": "纯向量 (Baseline)", "hybrid": False, "merge": False, "rerank": False},
            {"name": "B", "desc": "混合检索 (Hybrid)", "hybrid": True, "merge": False, "rerank": False},
            {"name": "C", "desc": "自动合并 (Auto-Merge)", "hybrid": True, "merge": True, "rerank": False},
            {"name": "D", "desc": "完全体 (Full)", "hybrid": True, "merge": True, "rerank": True},
        ]

    def run_experiment(self, config: Dict, dataset: pd.DataFrame) -> Tuple[Dict, List[Dict]]:
        """
        运行单组实验
        返回: (统计指标metrics, 详细记录details)
        """
        exp_tag = f"Exp_{config['name']}"
        print(f"\n🧪 启动实验 [{config['name']}]: {config['desc']}")

        retriever = self.service.get_retriever(
            enable_hybrid=config["hybrid"],
            enable_merge=config["merge"]
        )

        detailed_results = []  # 记录每一题的详细情况
        start_time = time.time()
        top_k = settings.rerank_top_k

        for idx, row in tqdm(dataset.iterrows(), total=len(dataset), unit="题", desc=exp_tag):
            query = str(row['Question'])
            ground_truth = str(row['Ground Truth Text'])
            category = str(row.get('Category', 'Unknown'))

            # 检索
            nodes = retriever.retrieve(query)

            # 重排
            if config["rerank"] and self.reranker:
                query_bundle = QueryBundle(query_str=query)
                ranked_nodes = self.reranker.postprocess_nodes(nodes, query_bundle)
                final_nodes = ranked_nodes[:top_k]
            else:
                final_nodes = nodes[:top_k]

            # 判分
            relevance_scores = []
            hit_rank = -1

            # 👇 [修改] 增加判空检查，防止 list index out of range
            if final_nodes and len(final_nodes) > 0:
                top1_text = final_nodes[0].text
            else:
                top1_text = "无结果"

            for rank, node in enumerate(final_nodes):
                is_hit = self.judge.is_hit(ground_truth, node.text)
                relevance_scores.append(1 if is_hit else 0)
                if is_hit and hit_rank == -1:
                    hit_rank = rank + 1

            if len(relevance_scores) < top_k:
                relevance_scores += [0] * (top_k - len(relevance_scores))

            # 计算单题指标
            is_hit_int = 1 if hit_rank > 0 else 0
            mrr = 1.0 / hit_rank if hit_rank > 0 else 0.0
            ndcg = calculate_ndcg(top_k, relevance_scores)

            # 记录详情 (用于写 Case Study)
            detailed_results.append({
                "Experiment": config["name"],
                "Category": category,
                "Question": query,
                "Is_Hit": is_hit_int,
                "MRR": mrr,
                "NDCG": ndcg,
                "Ground_Truth": ground_truth,
                "Top1_Retrieved": top1_text[:100] + "..."  # 只存前100字预览
            })

        avg_latency = ((time.time() - start_time) * 1000) / len(dataset)
        df_res = pd.DataFrame(detailed_results)

        metrics = {
            "Experiment": config["name"],
            "Description": config["desc"],
            "Hit_Rate": df_res["Is_Hit"].mean(),
            "MRR": df_res["MRR"].mean(),
            "NDCG": df_res["NDCG"].mean(),
            "Latency(ms)": avg_latency
        }

        return metrics, detailed_results

    def run(self, limit: int = None, target_exp: str = None):
        # 生成带时间戳的文件名 (核心修改)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = project_root / "tests" / "data" / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)  # 自动创建 reports 文件夹

        suffix = f"_limit{limit}" if limit else "_full"
        summary_file = output_dir / f"report_summary_{timestamp}{suffix}.csv"
        details_file = output_dir / f"report_details_{timestamp}{suffix}.csv"

        # 加载数据
        data_path = project_root / "tests" / "data" / "test_dataset.csv"
        if not data_path.exists():
            print(f"❌ 错误: 找不到 {data_path}")
            return

        try:
            df = pd.read_csv(data_path, encoding='utf-8-sig')
        except:
            df = pd.read_csv(data_path, encoding='gbk')

        if limit:
            print(f"✂️  测试模式: 仅截取前 {limit} 条")
            df = df.head(limit)

        print(f"📊 测试集: {len(df)} 条 | 🕒 任务ID: {timestamp}")

        # 实验筛选
        experiments_to_run = self.configs
        if target_exp:
            experiments_to_run = [c for c in self.configs if c["name"].lower() == target_exp.lower()]
            if not experiments_to_run:
                print(f"❌ 错误: 未找到实验 '{target_exp}'")
                return

        # 运行
        all_metrics = []
        all_details = []

        for config in experiments_to_run:
            # 👇 [修改] 暂时注释掉 try-except 以便显示详细报错
            # try:
            metrics, details = self.run_experiment(config, df)
            all_metrics.append(metrics)
            all_details.extend(details)
            print(f"   👉 结果: Hit={metrics['Hit_Rate']:.2%} | MRR={metrics['MRR']:.4f}")
            # except Exception as e:
            #     print(f"❌ 实验 {config['name']} 失败: {e}")

        # 保存结果 (无论是否 limit，都保存！)
        if all_metrics:
            # 1. 保存汇总表
            final_df = pd.DataFrame(all_metrics)
            print("\n" + "=" * 80)
            print("🏆 实验汇总报告")
            print("=" * 80)
            print(final_df.to_string(index=False, float_format=lambda x: "{:.4f}".format(x)))

            final_df.to_csv(summary_file, index=False, encoding='utf-8-sig')
            print(f"\n✅ 汇总报表已保存: {summary_file}")

            # 2. 保存明细表 (Case Study 素材)
            details_df = pd.DataFrame(all_details)
            details_df.to_csv(details_file, index=False, encoding='utf-8-sig')
            print(f"✅ 详细记录已保存: {details_file}")
            print(f"   (包含每一道题的得分和检索内容，可用于论文案例分析)")
        else:
            print("\n⚠️ 无实验结果生成")


if __name__ == "__main__":
    os.environ["no_proxy"] = "localhost,127.0.0.1"

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="仅测试前 N 条")
    parser.add_argument("--exp", type=str, default=None, help="指定实验 (A/B/C/D)")

    args = parser.parse_args()

    runner = ExperimentRunner()
    runner.run(limit=args.limit, target_exp=args.exp)