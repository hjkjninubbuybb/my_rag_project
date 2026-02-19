"""
检索评测脚本。

支持两种模式:
1. 单配置评测: --config configs/default.yaml
2. 消融矩阵评测: --grid configs/ablation_grid.yaml
"""

import sys
import os
import argparse
import unicodedata
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv

# --- 环境初始化 ---
os.environ["no_proxy"] = "localhost,127.0.0.1,::1"
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

current_file_path = Path(__file__).resolve()
project_root = current_file_path.parent.parent
sys.path.insert(0, str(project_root / "src"))

env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)

# 触发组件自动注册
import rag.components  # noqa: F401

from rag.config.experiment import ExperimentConfig, ExperimentGrid
from rag.config.settings import settings
from rag.components.providers.bgem3 import SparseModelManager
from rag.experiment.runner import BatchExperimentRunner
from rag.experiment.results import ResultsCollector


# --- 视觉对齐工具 ---

def get_visual_width(s: str) -> int:
    width = 0
    for ch in str(s):
        if unicodedata.east_asian_width(ch) in ("W", "F", "A"):
            width += 2
        else:
            width += 1
    return width


def pad_visual(s: str, width: int, align: str = "left") -> str:
    s = str(s)
    vis_w = get_visual_width(s)
    pad_len = max(0, width - vis_w)
    if align == "left":
        return s + " " * pad_len
    elif align == "right":
        return " " * pad_len + s
    else:
        left = pad_len // 2
        right = pad_len - left
        return " " * left + s + " " * right


def print_aligned_table(data: List[Dict], headers: Dict[str, int]):
    header_row = "|"
    for title, width in headers.items():
        header_row += f" {pad_visual(title, width, 'center')} |"
    border = "+" + "+".join(["-" * (w + 2) for w in headers.values()]) + "+"
    print(border)
    print(header_row)
    print(border)
    for item in data:
        row_str = "|"
        for key, width in headers.items():
            val = item.get(key, "")
            align = "right" if isinstance(val, (int, float)) else "center"
            row_str += f" {pad_visual(val, width, align)} |"
        print(row_str)
    print(border)


# --- CLI ---

def parse_args():
    parser = argparse.ArgumentParser(description="RAG 检索评测工具")
    parser.add_argument("--config", type=str, default=None, help="单实验 YAML 配置")
    parser.add_argument("--grid", type=str, default=None, help="消融矩阵 YAML 配置")
    parser.add_argument("--dataset", type=str, default="tests/data/test_dataset.csv", help="测试数据集路径")
    parser.add_argument("--limit", type=int, default=None, help="仅测试前 N 条")
    return parser.parse_args()


def main():
    args = parse_args()

    api_key = os.getenv("DASHSCOPE_API_KEY", "")

    # 构建实验配置列表
    if args.grid:
        print(f"[Mode] 消融矩阵: {args.grid}")
        grid = ExperimentGrid.from_yaml(args.grid)
        configs = grid.generate_configs(api_key=api_key)
        print(f"[Grid] 共 {grid.total_combinations} 个实验组合")
    elif args.config:
        print(f"[Mode] 单实验: {args.config}")
        cfg = ExperimentConfig.from_yaml(args.config, api_key=api_key)
        configs = [cfg]
    else:
        # 默认: 使用 settings + 4 组检索消融
        settings.load_experiment_config("configs/default.yaml")
        base = settings.to_experiment_config()
        configs = []
        ablation_options = [
            {"enable_hybrid": False, "enable_auto_merge": False, "enable_rerank": False, "tag": "baseline"},
            {"enable_hybrid": False, "enable_auto_merge": True, "enable_rerank": True, "tag": "no_hybrid"},
            {"enable_hybrid": True, "enable_auto_merge": True, "enable_rerank": False, "tag": "no_rerank"},
            {"enable_hybrid": True, "enable_auto_merge": True, "enable_rerank": True, "tag": "full"},
        ]
        for opt in ablation_options:
            tag = opt.pop("tag")
            configs.append(ExperimentConfig(
                **{**base.to_full_dict(), **opt, "experiment_id": tag, "experiment_description": tag},
            ))

    # 预热稀疏向量分词器 (如果有任何配置需要 hybrid)
    if any(c.enable_hybrid for c in configs):
        print("[Warmup] 初始化中文分词器...")
        SparseModelManager.warmup()

    # 运行评测
    dataset_path = str(project_root / args.dataset)
    runner = BatchExperimentRunner(
        configs=configs,
        dataset_path=dataset_path,
        input_dir="",
    )
    summaries, details = runner.run_evaluation(limit=args.limit)

    # 保存结果
    collector = ResultsCollector(output_dir=str(project_root / "data" / "reports"))
    if summaries:
        paths = collector.save_batch(summaries, details, tag="eval")

        # 打印汇总表格
        print("\n" + "=" * 100)
        print("消融实验报告")
        headers = {
            "experiment_id": 20,
            "description": 30,
            "hit_rate": 10,
            "mrr": 10,
            "ndcg": 10,
            "avg_latency_ms": 14,
        }
        table_data = []
        for s in summaries:
            table_data.append({
                "experiment_id": s["experiment_id"],
                "description": s["description"],
                "hit_rate": f"{s['hit_rate']:.4f}",
                "mrr": f"{s['mrr']:.4f}",
                "ndcg": f"{s['ndcg']:.4f}",
                "avg_latency_ms": f"{s['avg_latency_ms']:.1f} ms",
            })
        print_aligned_table(table_data, headers)
        print("=" * 100)
        print(f"\n结果已保存: {paths['summary']}")
    else:
        print("\n无结果生成")


if __name__ == "__main__":
    main()
