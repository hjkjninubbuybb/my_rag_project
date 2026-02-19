"""
实验配置管理。

ExperimentConfig: 单次实验的不可变配置（frozen dataclass）。
ExperimentGrid: 消融实验矩阵，自动生成参数笛卡尔积。
"""

from __future__ import annotations

import hashlib
import itertools
import os
from dataclasses import dataclass, field, fields, asdict
from pathlib import Path
from typing import Optional, List, Dict, Any

import yaml


# ── 密钥字段名集合（序列化时排除）──────────────────────
_SECRET_FIELDS = {"dashscope_api_key"}


@dataclass(frozen=True)
class ExperimentConfig:
    """单次实验的完整配置（不可变）。

    所有实验维度（模型、切片、检索、存储）集中定义于此。
    Pipeline 中的各组件通过此对象获取参数，而非读取全局 settings。
    """

    # ── 实验元数据 ──
    experiment_id: str = "default"
    experiment_description: str = "Default Configuration"

    # ── 模型供应商 ──
    llm_provider: str = "dashscope"
    llm_model: str = "qwen-plus"
    llm_temperature: float = 0.1
    embedding_provider: str = "dashscope"
    embedding_model: str = "text-embedding-v4"
    embedding_dim: int = 1536
    reranker_provider: str = "dashscope"
    reranker_model: str = "gte-rerank"

    # ── 存储 ──
    qdrant_path: str = "data/vectordb"
    collection_name_override: Optional[str] = None

    # ── 切片参数（影响入库 fingerprint）──
    chunking_strategy: str = "fixed"
    chunk_size_parent: int = 1024
    chunk_size_child: int = 256
    chunk_overlap: int = 50

    # ── 检索参数（不影响入库）──
    enable_hybrid: bool = True
    hybrid_alpha: float = 0.5
    enable_auto_merge: bool = True
    enable_rerank: bool = True
    retrieval_top_k: int = 50
    rerank_top_k: int = 5

    # ── 密钥（不序列化）──
    dashscope_api_key: str = ""

    # ──────────────────── 派生属性 ────────────────────

    @property
    def ingestion_fingerprint(self) -> str:
        """入库指纹: 相同指纹的实验共享同一个 Qdrant collection。

        由切片参数 + embedding 模型唯一决定。
        """
        parts = (
            self.chunking_strategy,
            str(self.chunk_size_parent),
            str(self.chunk_size_child),
            str(self.chunk_overlap),
            self.embedding_provider,
            self.embedding_model,
            str(self.embedding_dim),
        )
        raw = "|".join(parts)
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    @property
    def collection_name(self) -> str:
        """自动生成或使用手动 override 的 collection 名称。"""
        if self.collection_name_override:
            return self.collection_name_override
        return f"exp_{self.ingestion_fingerprint}"

    # ──────────────────── 序列化 ────────────────────

    def to_display_dict(self) -> Dict[str, Any]:
        """返回不含密钥字段的字典，用于 UI 展示和日志输出。"""
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if f.name not in _SECRET_FIELDS
        }

    def to_full_dict(self) -> Dict[str, Any]:
        """返回完整字典（含密钥），用于内部传参。"""
        return asdict(self)

    # ──────────────────── 工厂方法 ────────────────────

    @classmethod
    def from_yaml(cls, path: str, api_key: str = "") -> "ExperimentConfig":
        """从单实验 YAML 配置文件加载，向后兼容现有 default.yaml 格式。"""
        config_path = Path(path).resolve()
        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        kwargs: Dict[str, Any] = {}

        # 密钥: 优先参数传入 > 环境变量
        kwargs["dashscope_api_key"] = api_key or os.getenv("DASHSCOPE_API_KEY", "")

        # experiment 段
        if "experiment" in data:
            exp = data["experiment"]
            kwargs["experiment_id"] = exp.get("id", cls.experiment_id)
            kwargs["experiment_description"] = exp.get("description", cls.experiment_description)

        # model 段
        if "model" in data:
            m = data["model"]
            kwargs["llm_provider"] = m.get("llm_provider", cls.llm_provider)
            kwargs["llm_model"] = m.get("llm_model", cls.llm_model)
            kwargs["llm_temperature"] = m.get("llm_temperature", cls.llm_temperature)
            kwargs["embedding_provider"] = m.get("embedding_provider", cls.embedding_provider)
            kwargs["embedding_model"] = m.get("embedding_model", cls.embedding_model)
            kwargs["embedding_dim"] = m.get("embedding_dim", cls.embedding_dim)
            kwargs["reranker_provider"] = m.get("reranker_provider", cls.reranker_provider)
            kwargs["reranker_model"] = m.get("reranker_model", cls.reranker_model)

        # storage 段
        if "storage" in data:
            s = data["storage"]
            kwargs["qdrant_path"] = s.get("qdrant_path", cls.qdrant_path)
            kwargs["collection_name_override"] = s.get("collection_name", None)

        # rag 段
        if "rag" in data:
            r = data["rag"]
            kwargs["chunking_strategy"] = r.get("chunking_strategy", cls.chunking_strategy)
            kwargs["chunk_size_parent"] = r.get("chunk_size_parent", cls.chunk_size_parent)
            kwargs["chunk_size_child"] = r.get("chunk_size_child", cls.chunk_size_child)
            kwargs["chunk_overlap"] = r.get("chunk_overlap", cls.chunk_overlap)
            kwargs["retrieval_top_k"] = r.get("retrieval_top_k", cls.retrieval_top_k)
            kwargs["rerank_top_k"] = r.get("rerank_top_k", cls.rerank_top_k)

        # retrieval 段 (新增, 可选)
        if "retrieval" in data:
            ret = data["retrieval"]
            kwargs["enable_hybrid"] = ret.get("enable_hybrid", cls.enable_hybrid)
            kwargs["hybrid_alpha"] = ret.get("hybrid_alpha", cls.hybrid_alpha)
            kwargs["enable_auto_merge"] = ret.get("enable_auto_merge", cls.enable_auto_merge)
            kwargs["enable_rerank"] = ret.get("enable_rerank", cls.enable_rerank)

        return cls(**kwargs)

    def __str__(self) -> str:
        return (
            f"ExperimentConfig(id={self.experiment_id}, "
            f"chunker={self.chunking_strategy}, "
            f"child={self.chunk_size_child}, overlap={self.chunk_overlap}, "
            f"hybrid={self.enable_hybrid}, auto_merge={self.enable_auto_merge}, "
            f"rerank={self.enable_rerank}, "
            f"collection={self.collection_name})"
        )


@dataclass
class ExperimentGrid:
    """消融实验矩阵定义。

    每个维度是一个 list，generate_configs() 生成所有组合的笛卡尔积。
    """

    # ── 切片维度 ──
    chunking_strategies: List[str] = field(default_factory=lambda: ["fixed"])
    chunk_sizes_child: List[int] = field(default_factory=lambda: [256])
    chunk_overlaps: List[int] = field(default_factory=lambda: [50])
    chunk_sizes_parent: List[int] = field(default_factory=lambda: [1024])

    # ── 检索维度 ──
    enable_hybrid: List[bool] = field(default_factory=lambda: [True])
    enable_auto_merge: List[bool] = field(default_factory=lambda: [True])
    enable_rerank: List[bool] = field(default_factory=lambda: [True])

    # ── 模型维度 ──
    llm_models: List[str] = field(default_factory=lambda: ["qwen-plus"])
    embedding_models: List[str] = field(default_factory=lambda: ["text-embedding-v4"])
    reranker_models: List[str] = field(default_factory=lambda: ["gte-rerank"])

    # ── 固定参数（不参与笛卡尔积）──
    llm_provider: str = "dashscope"
    embedding_provider: str = "dashscope"
    reranker_provider: str = "dashscope"
    embedding_dim: int = 1536
    llm_temperature: float = 0.1
    qdrant_path: str = "data/vectordb"
    retrieval_top_k: int = 50
    rerank_top_k: int = 5

    @property
    def total_combinations(self) -> int:
        """总实验组合数。"""
        return (
            len(self.chunking_strategies)
            * len(self.chunk_sizes_child)
            * len(self.chunk_overlaps)
            * len(self.chunk_sizes_parent)
            * len(self.enable_hybrid)
            * len(self.enable_auto_merge)
            * len(self.enable_rerank)
            * len(self.llm_models)
            * len(self.embedding_models)
            * len(self.reranker_models)
        )

    def generate_configs(self, api_key: str = "") -> List[ExperimentConfig]:
        """生成所有参数组合的 ExperimentConfig 列表。"""
        api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")

        product = itertools.product(
            self.chunking_strategies,
            self.chunk_sizes_child,
            self.chunk_overlaps,
            self.chunk_sizes_parent,
            self.enable_hybrid,
            self.enable_auto_merge,
            self.enable_rerank,
            self.llm_models,
            self.embedding_models,
            self.reranker_models,
        )

        configs = []
        for idx, combo in enumerate(product, start=1):
            (
                strategy, child_size, overlap, parent_size,
                hybrid, auto_merge, rerank,
                llm_model, emb_model, reranker_model,
            ) = combo

            config = ExperimentConfig(
                experiment_id=f"ablation_{idx:04d}",
                experiment_description=(
                    f"{strategy}_c{child_size}_o{overlap}"
                    f"_h{'Y' if hybrid else 'N'}"
                    f"_m{'Y' if auto_merge else 'N'}"
                    f"_r{'Y' if rerank else 'N'}"
                ),
                llm_provider=self.llm_provider,
                llm_model=llm_model,
                llm_temperature=self.llm_temperature,
                embedding_provider=self.embedding_provider,
                embedding_model=emb_model,
                embedding_dim=self.embedding_dim,
                reranker_provider=self.reranker_provider,
                reranker_model=reranker_model,
                qdrant_path=self.qdrant_path,
                chunking_strategy=strategy,
                chunk_size_parent=parent_size,
                chunk_size_child=child_size,
                chunk_overlap=overlap,
                enable_hybrid=hybrid,
                enable_auto_merge=auto_merge,
                enable_rerank=rerank,
                retrieval_top_k=self.retrieval_top_k,
                rerank_top_k=self.rerank_top_k,
                dashscope_api_key=api_key,
            )
            configs.append(config)

        return configs

    @classmethod
    def from_yaml(cls, path: str) -> "ExperimentGrid":
        """从消融矩阵 YAML 文件加载。"""
        config_path = Path(path).resolve()
        if not config_path.exists():
            raise FileNotFoundError(f"消融配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        grid_data = data.get("grid", {})
        fixed_data = data.get("fixed", {})

        kwargs: Dict[str, Any] = {}

        # 网格维度
        if "chunking_strategies" in grid_data:
            kwargs["chunking_strategies"] = grid_data["chunking_strategies"]
        if "chunk_sizes_child" in grid_data:
            kwargs["chunk_sizes_child"] = grid_data["chunk_sizes_child"]
        if "chunk_overlaps" in grid_data:
            kwargs["chunk_overlaps"] = grid_data["chunk_overlaps"]
        if "chunk_sizes_parent" in grid_data:
            kwargs["chunk_sizes_parent"] = grid_data["chunk_sizes_parent"]
        if "enable_hybrid" in grid_data:
            kwargs["enable_hybrid"] = grid_data["enable_hybrid"]
        if "enable_auto_merge" in grid_data:
            kwargs["enable_auto_merge"] = grid_data["enable_auto_merge"]
        if "enable_rerank" in grid_data:
            kwargs["enable_rerank"] = grid_data["enable_rerank"]
        if "llm_models" in grid_data:
            kwargs["llm_models"] = grid_data["llm_models"]
        if "embedding_models" in grid_data:
            kwargs["embedding_models"] = grid_data["embedding_models"]
        if "reranker_models" in grid_data:
            kwargs["reranker_models"] = grid_data["reranker_models"]

        # 固定参数
        if "llm_provider" in fixed_data:
            kwargs["llm_provider"] = fixed_data["llm_provider"]
        if "embedding_provider" in fixed_data:
            kwargs["embedding_provider"] = fixed_data["embedding_provider"]
        if "reranker_provider" in fixed_data:
            kwargs["reranker_provider"] = fixed_data["reranker_provider"]
        if "embedding_dim" in fixed_data:
            kwargs["embedding_dim"] = fixed_data["embedding_dim"]
        if "llm_temperature" in fixed_data:
            kwargs["llm_temperature"] = fixed_data["llm_temperature"]
        if "qdrant_path" in fixed_data:
            kwargs["qdrant_path"] = fixed_data["qdrant_path"]
        if "retrieval_top_k" in fixed_data:
            kwargs["retrieval_top_k"] = fixed_data["retrieval_top_k"]
        if "rerank_top_k" in fixed_data:
            kwargs["rerank_top_k"] = fixed_data["rerank_top_k"]

        return cls(**kwargs)
