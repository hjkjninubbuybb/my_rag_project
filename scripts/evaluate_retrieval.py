"""
[Architecture Role: Evaluation Layer (评测层)]
此脚本用于自动化评估 RAG 检索系统的准确率，是 "消融实验 (Ablation Study)" 的核心工具。

核心升级 (Engineering):
1. [Visual Alignment] 使用 unicodedata 手动计算字符视觉宽度，解决中英文混排导致的表格错位问题。
2. [Zero Dependency] 移除对 tabulate 的依赖，纯 Python 原生实现完美对齐。
3. [Metrics] 计算 Hit Rate, MRR, NDCG。
"""

import sys
import os
import time
import numpy as np
import pandas as pd
import argparse
import unicodedata
from datetime import datetime
from pathlib import Path
from tqdm import tqdm
from typing import List, Dict, Tuple
from dotenv import load_dotenv

# --- 1. 环境初始化 ---
os.environ["no_proxy"] = "localhost,127.0.0.1,::1"

current_file_path = Path(__file__).resolve()
project_root = current_file_path.parent.parent
sys.path.insert(0, str(project_root))

env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)

from app.core.engine.retrieval import RetrievalService
from app.core.engine.factory import ModelFactory
from app.settings import settings
from llama_index.core.schema import QueryBundle


# --- 2. 视觉对齐工具 (核心修复) ---

def get_visual_width(s: str) -> int:
    """
    计算字符串在终端显示的视觉宽度
    中文 = 2, 英文/数字 = 1
    """
    width = 0
    for ch in str(s):
        # East_Asian_Width:
        # 'W' (Wide) = 中文/日文等
        # 'F' (Fullwidth) = 全角字符
        # 'A' (Ambiguous) = 某些特殊符号，通常在终端也占2格
        if unicodedata.east_asian_width(ch) in ('W', 'F', 'A'):
            width += 2
        else:
            width += 1
    return width

def pad_visual(s: str, width: int, align: str = 'left') -> str:
    """
    根据视觉宽度进行填充
    """
    s = str(s)
    vis_w = get_visual_width(s)
    pad_len = max(0, width - vis_w)

    if align == 'left':
        return s + ' ' * pad_len
    elif align == 'right':
        return ' ' * pad_len + s
    else: # center
        left = pad_len // 2
        right = pad_len - left
        return ' ' * left + s + ' ' * right

def print_aligned_table(data: List[Dict], headers: Dict[str, int]):
    """
    打印完美对齐的表格
    headers: { '字段名': 目标列宽 }
    """
    # 1. 打印表头
    header_row = "|"
    for title, width in headers.items():
        header_row += f" {pad_visual(title, width, 'center')} |"

    border = "+" + "+".join(["-" * (w + 2) for w in headers.values()]) + "+"

    print(border)
    print(header_row)
    print(border)

    # 2. 打印数据行
    for item in data:
        row_str = "|"
        for key, width in headers.items():
            val = item.get(key, "")
            # 数字靠右，文字靠左/居中
            align = 'right' if isinstance(val, (int, float)) and 'Rate' not in key else 'center'
            row_str += f" {pad_visual(val, width, align)} |"
        print(row_str)

    print(border)


# --- 3. 数学工具 ---

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


# --- 4. 语义裁判 ---

class SemanticJudge:
    def __init__(self):
        print("⚖️ [Judge] 初始化语义裁判...")
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


# --- 5. 实验控制器 ---

class ExperimentRunner:
    def __init__(self):
        print(f"\n🛠️ [System] 初始化评测 | 实验ID: {settings.experiment_id}")
        print(f"   -> 集合: {settings.collection_name}")
        self.service = RetrievalService()
        self.judge = SemanticJudge()
        self.reranker = self.service.reranker

        # 检查集合
        try:
            client = self.service.store_manager.client
            if client.collection_exists(settings.collection_name):
                cnt = client.count(settings.collection_name).count
                if cnt == 0:
                    print(f"⚠️ [警告] 集合 '{settings.collection_name}' 为空！请先运行 main.py 入库。")
                else:
                    print(f"✅ [Check] 集合包含 {cnt} 条数据")
        except:
            pass

        self.configs = [
            {"name": "A", "desc": "纯向量 (Baseline)", "hybrid": False, "merge": False, "rerank": False},
            {"name": "B", "desc": "无混合检索 (No Hybrid)", "hybrid": False, "merge": True, "rerank": True},
            {"name": "C", "desc": "无重排序 (No Rerank)", "hybrid": True, "merge": True, "rerank": False},
            {"name": "D", "desc": "完全体 (Full Pipeline)", "hybrid": True, "merge": True, "rerank": True},
        ]

    def run_experiment(self, config: Dict, dataset: pd.DataFrame) -> Tuple[Dict, List[Dict]]:
        exp_tag = f"Exp_{config['name']}"
        print(f"\n🧪 启动子实验 [{config['name']}]: {config['desc']}")

        retriever = self.service.get_retriever(
            enable_hybrid=config["hybrid"],
            enable_merge=config["merge"]
        )

        detailed_results = []
        start_time = time.time()
        top_k = settings.rerank_top_k

        for idx, row in tqdm(dataset.iterrows(), total=len(dataset), unit="题", desc=exp_tag):
            query = str(row['Question'])
            ground_truth = str(row['Ground Truth Text'])
            category = str(row.get('Category', 'Unknown'))

            try:
                nodes = retriever.retrieve(query)

                if config["rerank"] and self.reranker:
                    query_bundle = QueryBundle(query_str=query)
                    ranked_nodes = self.reranker.postprocess_nodes(nodes, query_bundle)
                    final_nodes = ranked_nodes[:top_k]
                else:
                    final_nodes = nodes[:top_k]

                relevance_scores = []
                hit_rank = -1

                # Top 5
                retrieved_snippets = []
                if final_nodes:
                    for i, node in enumerate(final_nodes[:5]):
                        clean_text = node.text[:80].replace("\n", " ").replace("\r", " ")
                        retrieved_snippets.append(f"[{i + 1}] {clean_text}...")
                    top5_text_combined = "\n".join(retrieved_snippets)
                else:
                    top5_text_combined = "无结果"

                for rank, node in enumerate(final_nodes):
                    is_hit = self.judge.is_hit(ground_truth, node.text)
                    relevance_scores.append(1 if is_hit else 0)
                    if is_hit and hit_rank == -1:
                        hit_rank = rank + 1

                if len(relevance_scores) < top_k:
                    relevance_scores += [0] * (top_k - len(relevance_scores))

                is_hit_int = 1 if hit_rank > 0 else 0
                mrr = 1.0 / hit_rank if hit_rank > 0 else 0.0
                ndcg = calculate_ndcg(top_k, relevance_scores)

                detailed_results.append({
                    "Experiment": config["name"],
                    "Category": category,
                    "Question": query,
                    "Is_Hit": is_hit_int,
                    "MRR": mrr,
                    "NDCG": ndcg,
                    "Ground_Truth": ground_truth,
                    "Retrieved_Top5": top5_text_combined
                })

            except Exception as e:
                print(f"❌ Error: {e}")
                detailed_results.append({
                    "Experiment": config["name"],
                    "Category": category,
                    "Question": query,
                    "Is_Hit": 0, "MRR": 0, "NDCG": 0,
                    "Ground_Truth": ground_truth,
                    "Retrieved_Top5": f"Error: {e}"
                })

        avg_latency = ((time.time() - start_time) * 1000) / len(dataset)

        metrics = {
            "Experiment": config["name"],
            "Description": config["desc"],
            "Hit_Rate": f"{pd.DataFrame(detailed_results)['Is_Hit'].mean():.4f}",
            "MRR": f"{pd.DataFrame(detailed_results)['MRR'].mean():.4f}",
            "NDCG": f"{pd.DataFrame(detailed_results)['NDCG'].mean():.4f}",
            "Latency": f"{avg_latency:.1f} ms"
        }

        return metrics, detailed_results

    def run(self, limit: int = None, target_exp: str = None):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        exp_id_safe = settings.experiment_id.replace(" ", "_")

        output_dir = project_root / "tests" / "data" / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)

        suffix = f"_limit{limit}" if limit else "_full"
        summary_file = output_dir / f"report_{exp_id_safe}_summary_{timestamp}{suffix}.csv"
        details_file = output_dir / f"report_{exp_id_safe}_details_{timestamp}{suffix}.csv"

        data_path = project_root / "tests" / "data" / "test_dataset.csv"
        if not data_path.exists():
            print(f"❌ 找不到测试集: {data_path}")
            return

        try:
            df = pd.read_csv(data_path, encoding='utf-8-sig')
        except:
            df = pd.read_csv(data_path, encoding='gbk')

        if limit:
            print(f"✂️  Debug模式: 前 {limit} 条")
            df = df.head(limit)

        experiments_to_run = self.configs
        if target_exp:
            experiments_to_run = [c for c in self.configs if c["name"].lower() == target_exp.lower()]

        all_metrics = []
        all_details = []

        for config in experiments_to_run:
            try:
                metrics, details = self.run_experiment(config, df)
                all_metrics.append(metrics)
                all_details.extend(details)
            except Exception as e:
                print(f"❌ 实验 {config['name']} 失败: {e}")

        if all_metrics:
            print("\n")
            print("=" * 100)
            print(f"🏆 消融实验报告 | ID: {settings.experiment_id}")

            # --- 手动对齐表格打印 ---
            # 定义每一列的视觉宽度
            headers = {
                "Experiment": 12,
                "Description": 30, # 给描述留宽一点
                "Hit_Rate": 10,
                "MRR": 10,
                "NDCG": 10,
                "Latency": 12
            }
            print_aligned_table(all_metrics, headers)

            print("=" * 100)

            # 保存 CSV
            final_df = pd.DataFrame(all_metrics)
            final_df.to_csv(summary_file, index=False, encoding='utf-8-sig')
            details_df = pd.DataFrame(all_details)
            details_df.to_csv(details_file, index=False, encoding='utf-8-sig')
            print(f"\n✅ 报表已保存至: {output_dir}")
        else:
            print("\n⚠️ 无结果生成")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="configs/default.yaml", help="指定配置")
    parser.add_argument("--limit", type=int, default=None, help="仅测试前 N 条")
    parser.add_argument("--exp", type=str, default=None, help="指定子实验 (A/B/C/D)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        settings.load_experiment_config(args.config)
        settings.qdrant_path = str(project_root / settings.qdrant_path)
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        sys.exit(1)

    runner = ExperimentRunner()
    runner.run(limit=args.limit, target_exp=args.exp)