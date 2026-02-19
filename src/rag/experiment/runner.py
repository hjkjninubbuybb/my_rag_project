"""
批量消融实验执行器。

核心特性:
- 按 ingestion_fingerprint 分组，相同 fingerprint 只入库一次（智能入库）。
- 为每个 ExperimentConfig 创建 RetrievalService 执行检索评测。
- 计算 Hit Rate / MRR / NDCG 指标。
- 支持断点续跑：跳过已有数据的 collection。
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import List, Dict, Tuple, Optional, Callable

import numpy as np
import pandas as pd
from tqdm import tqdm
from llama_index.core.schema import QueryBundle

from rag.config.experiment import ExperimentConfig
from rag.core.registry import ComponentRegistry
from rag.pipeline.ingestion import IngestionService
from rag.pipeline.retrieval import RetrievalService
from rag.storage.vectordb import VectorStoreManager


def calculate_ndcg(k: int, relevance_scores: List[int]) -> float:
    """计算 NDCG@k。"""
    scores = relevance_scores[:k]
    dcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(scores) if rel > 0)
    ideal_scores = sorted(scores, reverse=True)
    idcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(ideal_scores) if rel > 0)
    return dcg / idcg if idcg > 0 else 0.0


class SemanticJudge:
    """语义判定器：判断检索结果是否命中 ground truth。"""

    def __init__(self, config: ExperimentConfig):
        embedding_provider = ComponentRegistry.get_embedding_provider(config.embedding_provider)
        self.embed_model = embedding_provider.create_embedding(
            model_name=config.embedding_model,
            api_key=config.dashscope_api_key,
        )
        self._cache: Dict[str, List[float]] = {}

    def get_embedding(self, text: str) -> List[float]:
        if text not in self._cache:
            self._cache[text] = self.embed_model.get_text_embedding(text)
        return self._cache[text]

    def is_hit(self, ground_truth: str, retrieved_text: str, threshold: float = 0.85) -> bool:
        def clean(t):
            return str(t).replace(" ", "").replace("\n", "").lower()

        # 子串匹配快速通道
        if clean(ground_truth) in clean(retrieved_text):
            return True

        try:
            vec_gt = np.array(self.get_embedding(ground_truth))
            vec_ret = np.array(self.get_embedding(retrieved_text))
            norm_gt = np.linalg.norm(vec_gt)
            norm_ret = np.linalg.norm(vec_ret)
            if norm_gt == 0 or norm_ret == 0:
                return False
            sim = np.dot(vec_gt, vec_ret) / (norm_gt * norm_ret)
            return sim > threshold
        except Exception:
            return False


class BatchExperimentRunner:
    """批量消融实验执行器。"""

    def __init__(
        self,
        configs: List[ExperimentConfig],
        dataset_path: str,
        input_dir: str,
        progress_callback: Optional[Callable[[str], None]] = None,
    ):
        self.configs = configs
        self.dataset_path = dataset_path
        self.input_dir = input_dir
        self._log = progress_callback or print

    def _log_msg(self, msg: str):
        self._log(msg)

    async def run_ingestion(self):
        """智能入库：按 ingestion_fingerprint 分组，相同 fingerprint 只入库一次。"""
        groups: Dict[str, ExperimentConfig] = {}
        for cfg in self.configs:
            fp = cfg.ingestion_fingerprint
            if fp not in groups:
                groups[fp] = cfg

        self._log_msg(f"[Ingestion] 共 {len(self.configs)} 个实验配置，"
                       f"去重后需入库 {len(groups)} 个 collection")

        for fp, cfg in groups.items():
            store = VectorStoreManager(cfg)
            if store.collection_exists() and store.collection_point_count() > 0:
                self._log_msg(f"[Ingestion] 跳过已有数据: {cfg.collection_name} "
                               f"({store.collection_point_count()} points)")
                continue

            self._log_msg(f"[Ingestion] 开始入库: {cfg.collection_name} "
                           f"(strategy={cfg.chunking_strategy}, "
                           f"chunk={cfg.chunk_size_child}, overlap={cfg.chunk_overlap})")
            service = IngestionService(cfg)
            await service.process_directory(self.input_dir)
            self._log_msg(f"[Ingestion] 入库完成: {cfg.collection_name}")

    def run_evaluation(self, limit: Optional[int] = None) -> Tuple[List[Dict], List[Dict]]:
        """运行检索评测。

        Returns:
            (summary_list, detail_list): 摘要指标 + 逐条详情
        """
        # 加载数据集
        try:
            df = pd.read_csv(self.dataset_path, encoding="utf-8-sig")
        except Exception:
            df = pd.read_csv(self.dataset_path, encoding="gbk")

        if limit:
            df = df.head(limit)
            self._log_msg(f"[Eval] 使用数据集前 {limit} 条")

        all_summaries = []
        all_details = []

        for cfg in self.configs:
            self._log_msg(f"\n[Eval] 实验: {cfg.experiment_id} | {cfg.experiment_description}")

            try:
                summary, details = self._evaluate_single(cfg, df)
                all_summaries.append(summary)
                all_details.extend(details)
            except Exception as e:
                self._log_msg(f"[Eval] 实验 {cfg.experiment_id} 失败: {e}")

        return all_summaries, all_details

    def _evaluate_single(
        self, config: ExperimentConfig, dataset: pd.DataFrame
    ) -> Tuple[Dict, List[Dict]]:
        """对单个实验配置执行评测。"""
        service = RetrievalService(config)
        judge = SemanticJudge(config)

        retriever = service.get_retriever(
            enable_hybrid=config.enable_hybrid,
            enable_merge=config.enable_auto_merge,
        )

        reranker = service.reranker
        top_k = config.rerank_top_k
        detailed_results = []
        start_time = time.time()

        for _, row in tqdm(
            dataset.iterrows(),
            total=len(dataset),
            unit="q",
            desc=config.experiment_id,
        ):
            query = str(row["Question"])
            ground_truth = str(row["Ground Truth Text"])
            category = str(row.get("Category", "Unknown"))

            try:
                nodes = retriever.retrieve(query)

                if config.enable_rerank and reranker:
                    query_bundle = QueryBundle(query_str=query)
                    ranked_nodes = reranker.postprocess_nodes(nodes, query_bundle)
                    final_nodes = ranked_nodes[:top_k]
                else:
                    final_nodes = nodes[:top_k]

                relevance_scores = []
                hit_rank = -1

                for rank, node in enumerate(final_nodes):
                    is_hit = judge.is_hit(ground_truth, node.text)
                    relevance_scores.append(1 if is_hit else 0)
                    if is_hit and hit_rank == -1:
                        hit_rank = rank + 1

                if len(relevance_scores) < top_k:
                    relevance_scores += [0] * (top_k - len(relevance_scores))

                is_hit_int = 1 if hit_rank > 0 else 0
                mrr = 1.0 / hit_rank if hit_rank > 0 else 0.0
                ndcg = calculate_ndcg(top_k, relevance_scores)

                # Top-5 snippet
                snippets = []
                for i, node in enumerate(final_nodes[:5]):
                    clean_text = node.text[:80].replace("\n", " ").replace("\r", " ")
                    snippets.append(f"[{i + 1}] {clean_text}...")

                detailed_results.append({
                    "Experiment": config.experiment_id,
                    "Description": config.experiment_description,
                    "Category": category,
                    "Question": query,
                    "Is_Hit": is_hit_int,
                    "MRR": mrr,
                    "NDCG": ndcg,
                    "Ground_Truth": ground_truth,
                    "Retrieved_Top5": "\n".join(snippets) if snippets else "N/A",
                })

            except Exception as e:
                detailed_results.append({
                    "Experiment": config.experiment_id,
                    "Description": config.experiment_description,
                    "Category": category,
                    "Question": query,
                    "Is_Hit": 0,
                    "MRR": 0.0,
                    "NDCG": 0.0,
                    "Ground_Truth": ground_truth,
                    "Retrieved_Top5": f"Error: {e}",
                })

        elapsed = time.time() - start_time
        avg_latency = (elapsed * 1000) / max(len(dataset), 1)
        df_results = pd.DataFrame(detailed_results)

        summary = {
            "experiment_id": config.experiment_id,
            "description": config.experiment_description,
            "chunking_strategy": config.chunking_strategy,
            "chunk_size_child": config.chunk_size_child,
            "chunk_overlap": config.chunk_overlap,
            "enable_hybrid": config.enable_hybrid,
            "enable_auto_merge": config.enable_auto_merge,
            "enable_rerank": config.enable_rerank,
            "collection_name": config.collection_name,
            "hit_rate": round(df_results["Is_Hit"].mean(), 4) if len(df_results) > 0 else 0,
            "mrr": round(df_results["MRR"].mean(), 4) if len(df_results) > 0 else 0,
            "ndcg": round(df_results["NDCG"].mean(), 4) if len(df_results) > 0 else 0,
            "avg_latency_ms": round(avg_latency, 1),
            "total_queries": len(dataset),
        }

        self._log_msg(
            f"[Result] {config.experiment_id}: "
            f"HitRate={summary['hit_rate']:.4f}, "
            f"MRR={summary['mrr']:.4f}, "
            f"NDCG={summary['ndcg']:.4f}, "
            f"Latency={summary['avg_latency_ms']:.1f}ms"
        )

        return summary, detailed_results
