"""
实验结果收集与持久化。

负责将实验结果保存为 CSV / JSON，并提供加载历史结果的接口。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

import pandas as pd


class ResultsCollector:
    """实验结果收集器。"""

    def __init__(self, output_dir: str = "data/reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_batch(
        self,
        summaries: List[Dict],
        details: List[Dict],
        tag: str = "",
    ) -> Dict[str, str]:
        """保存一批实验结果。

        Returns:
            包含各文件路径的字典。
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{tag}" if tag else ""

        summary_path = self.output_dir / f"summary_{timestamp}{suffix}.csv"
        detail_path = self.output_dir / f"details_{timestamp}{suffix}.csv"
        meta_path = self.output_dir / f"meta_{timestamp}{suffix}.json"

        # Summary CSV
        if summaries:
            pd.DataFrame(summaries).to_csv(summary_path, index=False, encoding="utf-8-sig")

        # Detail CSV
        if details:
            pd.DataFrame(details).to_csv(detail_path, index=False, encoding="utf-8-sig")

        # Meta JSON
        meta = {
            "timestamp": timestamp,
            "tag": tag,
            "num_experiments": len(summaries),
            "num_queries": details[0].get("total_queries", len(details)) if details else 0,
            "summary_file": str(summary_path),
            "detail_file": str(detail_path),
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        return {
            "summary": str(summary_path),
            "details": str(detail_path),
            "meta": str(meta_path),
        }

    def load_all_summaries(self) -> pd.DataFrame:
        """加载所有历史 summary CSV 并合并为一个 DataFrame。"""
        files = sorted(self.output_dir.glob("summary_*.csv"))
        if not files:
            return pd.DataFrame()

        frames = []
        for f in files:
            try:
                df = pd.read_csv(f, encoding="utf-8-sig")
                df["_source_file"] = f.name
                frames.append(df)
            except Exception:
                continue

        if not frames:
            return pd.DataFrame()

        return pd.concat(frames, ignore_index=True)

    def get_comparison_dataframe(self, summaries: Optional[List[Dict]] = None) -> pd.DataFrame:
        """获取用于 Gradio UI 展示的对比 DataFrame。

        如果传入 summaries 则直接使用，否则加载历史结果。
        """
        if summaries:
            df = pd.DataFrame(summaries)
        else:
            df = self.load_all_summaries()

        if df.empty:
            return df

        # 选择展示列
        display_cols = [
            "experiment_id", "description",
            "chunking_strategy", "chunk_size_child", "chunk_overlap",
            "enable_hybrid", "enable_auto_merge", "enable_rerank",
            "hit_rate", "mrr", "ndcg", "avg_latency_ms",
        ]
        available = [c for c in display_cols if c in df.columns]
        return df[available]
