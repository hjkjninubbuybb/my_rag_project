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
    qdrant_url: str = "http://localhost:6333"
    qdrant_path: str = "data/vectordb"
    mysql_url: str = "mysql+pymysql://rag_user:rag_password@localhost:3306/rag_db"
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "rag_user"
    mysql_password: str = "rag_password"
    mysql_database: str = "rag_db"
    collection_name_override: Optional[str] = None

    # ── 切片参数（影响入库 fingerprint）──
    chunking_strategy: str = "fixed"
    chunk_size_parent: int = 1024
    chunk_size_child: int = 256
    chunk_overlap: int = 50
    semantic_breakpoint_threshold: int = 95
    semantic_buffer_size: int = 1

    # ── 检索参数（不影响入库）──
    enable_hybrid: bool = True
    hybrid_alpha: float = 0.5
    enable_auto_merge: bool = True
    enable_rerank: bool = True
    retrieval_top_k: int = 50
    rerank_top_k: int = 5

    # ── 密钥（不序列化）──
    dashscope_api_key: str = ""

    # ── 多模态配置 ──
    enable_multimodal: bool = False
    multimodal_embedding_provider: str = "qwen-vl"
    multimodal_embedding_model: str = "qwen3-vl-embedding"
    multimodal_llm_model: str = "qwen-vl-max"
    image_embedding_dim: int = 2560

    # 图像处理参数
    image_max_size: int = 1024  # 最大边长(px)
    image_compression_quality: int = 85  # JPEG 压缩质量

    # 多模态检索参数
    image_vector_weight: float = 0.7  # 图像向量权重
    text_vector_weight: float = 0.3  # 文本向量权重

    # ── 角色权限过滤 ──
    user_role: Optional[str] = None  # "teacher" | "student" | "reviewer" | "defense_committee" | None（管理员，查看所有）

    # ── RAGAS 评估配置 ──
    enable_ragas_evaluation: bool = True
    ragas_metrics: List[str] = field(default_factory=lambda: [
        "context_precision",
        "context_recall",
    ])
    ragas_llm_provider: str = "dashscope"
    ragas_llm_model: str = "qwen-plus"

    # ──────────────────── 派生属性 ────────────────────

    @property
    def qdrant_endpoint(self) -> str:
        """获取 Qdrant 连接端点。优先使用 qdrant_url，若为空则 fallback 到 qdrant_path。"""
        if self.qdrant_url:
            return self.qdrant_url
        return self.qdrant_path

    @property
    def ingestion_fingerprint(self) -> str:
        """入库指纹: 相同指纹的实验共享同一个 Qdrant collection。

        由切片参数 + embedding 模型唯一决定。
        semantic 策略的切分结果由阈值 + buffer_size + embedding 决定，
        与 chunk_size / chunk_overlap 无关，因此使用不同的指纹组成。
        这确保消融网格中 semantic × 多个 chunk_size 不会产生重复 collection。

        多模态模式下，追加多模态参数到指纹中。
        """
        if self.chunking_strategy == "semantic":
            parts = (
                self.chunking_strategy,
                str(self.semantic_breakpoint_threshold),
                str(self.semantic_buffer_size),
                self.embedding_provider,
                self.embedding_model,
                str(self.embedding_dim),
            )
        else:
            parts = (
                self.chunking_strategy,
                str(self.chunk_size_parent),
                str(self.chunk_size_child),
                str(self.chunk_overlap),
                self.embedding_provider,
                self.embedding_model,
                str(self.embedding_dim),
            )

        # 追加多模态参数
        if self.enable_multimodal:
            parts = parts + (
                "multimodal",
                self.multimodal_embedding_provider,
                self.multimodal_embedding_model,
                str(self.image_embedding_dim),
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
            kwargs["qdrant_url"] = s.get("qdrant_url", cls.qdrant_url)
            kwargs["qdrant_path"] = s.get("qdrant_path", cls.qdrant_path)
            kwargs["mysql_url"] = s.get("mysql_url", cls.mysql_url)
            kwargs["collection_name_override"] = s.get("collection_name", None)

        # rag 段
        if "rag" in data:
            r = data["rag"]
            kwargs["chunking_strategy"] = r.get("chunking_strategy", cls.chunking_strategy)
            kwargs["chunk_size_parent"] = r.get("chunk_size_parent", cls.chunk_size_parent)
            kwargs["chunk_size_child"] = r.get("chunk_size_child", cls.chunk_size_child)
            kwargs["chunk_overlap"] = r.get("chunk_overlap", cls.chunk_overlap)
            kwargs["semantic_breakpoint_threshold"] = r.get(
                "semantic_breakpoint_threshold", cls.semantic_breakpoint_threshold
            )
            kwargs["semantic_buffer_size"] = r.get(
                "semantic_buffer_size", cls.semantic_buffer_size
            )
            kwargs["retrieval_top_k"] = r.get("retrieval_top_k", cls.retrieval_top_k)
            kwargs["rerank_top_k"] = r.get("rerank_top_k", cls.rerank_top_k)

        # retrieval 段 (可选)
        if "retrieval" in data:
            ret = data["retrieval"]
            kwargs["enable_hybrid"] = ret.get("enable_hybrid", cls.enable_hybrid)
            kwargs["hybrid_alpha"] = ret.get("hybrid_alpha", cls.hybrid_alpha)
            kwargs["enable_auto_merge"] = ret.get("enable_auto_merge", cls.enable_auto_merge)
            kwargs["enable_rerank"] = ret.get("enable_rerank", cls.enable_rerank)

        # ragas 段 (可选)
        if "ragas" in data:
            ragas_config = data["ragas"]
            kwargs["enable_ragas_evaluation"] = ragas_config.get("enable_evaluation", cls.enable_ragas_evaluation)
            kwargs["ragas_metrics"] = ragas_config.get("metrics", cls.ragas_metrics)
            kwargs["ragas_llm_provider"] = ragas_config.get("llm_provider", cls.ragas_llm_provider)
            kwargs["ragas_llm_model"] = ragas_config.get("llm_model", cls.ragas_llm_model)

        return cls(**kwargs)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentConfig":
        """从字典构建 ExperimentConfig，忽略未知字段。"""
        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

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
class StrategyParams:
    """单个切分策略的参数空间。

    size-based 策略（fixed/recursive/sentence）使用 chunk_sizes_child + chunk_overlaps。
    semantic 策略使用 breakpoint_thresholds + buffer_sizes。
    """

    chunk_sizes_child: List[int] = field(default_factory=lambda: [256])
    chunk_overlaps: List[int] = field(default_factory=lambda: [50])
    breakpoint_thresholds: List[int] = field(default_factory=lambda: [95])
    buffer_sizes: List[int] = field(default_factory=lambda: [1])


@dataclass
class ExperimentGrid:
    """消融实验矩阵定义。

    按策略分组生成配置：每个策略只和自己的参数做笛卡尔积，
    检索维度和模型维度在所有策略间共享。
    """

    # ── 按策略分组的参数空间 ──
    strategies: Dict[str, StrategyParams] = field(
        default_factory=lambda: {"fixed": StrategyParams()}
    )

    # ── 检索维度（所有策略共享）──
    enable_hybrid: List[bool] = field(default_factory=lambda: [True])
    enable_auto_merge: List[bool] = field(default_factory=lambda: [True])
    enable_rerank: List[bool] = field(default_factory=lambda: [True])

    # ── 模型维度（所有策略共享）──
    llm_models: List[str] = field(default_factory=lambda: ["qwen-plus"])
    embedding_models: List[str] = field(default_factory=lambda: ["text-embedding-v4"])
    reranker_models: List[str] = field(default_factory=lambda: ["gte-rerank"])

    # ── 固定参数（不参与笛卡尔积）──
    chunk_sizes_parent: List[int] = field(default_factory=lambda: [1024])
    llm_provider: str = "dashscope"
    embedding_provider: str = "dashscope"
    reranker_provider: str = "dashscope"
    embedding_dim: int = 1536
    llm_temperature: float = 0.1
    qdrant_url: str = "http://localhost:6333"
    qdrant_path: str = "data/vectordb"
    retrieval_top_k: int = 50
    rerank_top_k: int = 5

    @property
    def total_combinations(self) -> int:
        """总实验组合数。"""
        shared = (
            len(self.enable_hybrid)
            * len(self.enable_auto_merge)
            * len(self.enable_rerank)
            * len(self.llm_models)
            * len(self.embedding_models)
            * len(self.reranker_models)
        )

        strategy_combos = 0
        for name, params in self.strategies.items():
            if name == "semantic":
                strategy_combos += (
                    len(params.breakpoint_thresholds) * len(params.buffer_sizes)
                )
            else:
                strategy_combos += (
                    len(params.chunk_sizes_child)
                    * len(params.chunk_overlaps)
                    * len(self.chunk_sizes_parent)
                )

        return strategy_combos * shared

    def generate_configs(self, api_key: str = "") -> List[ExperimentConfig]:
        """按策略分组生成实验配置列表。"""
        api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")

        shared_dims = list(itertools.product(
            self.enable_hybrid,
            self.enable_auto_merge,
            self.enable_rerank,
            self.llm_models,
            self.embedding_models,
            self.reranker_models,
        ))

        configs: List[ExperimentConfig] = []
        idx = 0

        for strategy_name, params in self.strategies.items():
            if strategy_name == "semantic":
                strategy_dims = itertools.product(
                    params.breakpoint_thresholds,
                    params.buffer_sizes,
                )
                for threshold, buffer_size in strategy_dims:
                    for hybrid, auto_merge, rerank, llm, emb, reranker in shared_dims:
                        idx += 1
                        configs.append(ExperimentConfig(
                            experiment_id=f"ablation_{idx:04d}",
                            experiment_description=(
                                f"semantic_t{threshold}_b{buffer_size}"
                                f"_h{'Y' if hybrid else 'N'}"
                                f"_m{'Y' if auto_merge else 'N'}"
                                f"_r{'Y' if rerank else 'N'}"
                            ),
                            chunking_strategy="semantic",
                            chunk_size_parent=self.chunk_sizes_parent[0],
                            chunk_size_child=256,
                            chunk_overlap=50,
                            semantic_breakpoint_threshold=threshold,
                            semantic_buffer_size=buffer_size,
                            enable_hybrid=hybrid,
                            enable_auto_merge=auto_merge,
                            enable_rerank=rerank,
                            llm_provider=self.llm_provider,
                            llm_model=llm,
                            llm_temperature=self.llm_temperature,
                            embedding_provider=self.embedding_provider,
                            embedding_model=emb,
                            embedding_dim=self.embedding_dim,
                            reranker_provider=self.reranker_provider,
                            reranker_model=reranker,
                            qdrant_url=self.qdrant_url,
                            qdrant_path=self.qdrant_path,
                            retrieval_top_k=self.retrieval_top_k,
                            rerank_top_k=self.rerank_top_k,
                            dashscope_api_key=api_key,
                        ))
            else:
                strategy_dims = itertools.product(
                    params.chunk_sizes_child,
                    params.chunk_overlaps,
                    self.chunk_sizes_parent,
                )
                for child_size, overlap, parent_size in strategy_dims:
                    for hybrid, auto_merge, rerank, llm, emb, reranker in shared_dims:
                        idx += 1
                        configs.append(ExperimentConfig(
                            experiment_id=f"ablation_{idx:04d}",
                            experiment_description=(
                                f"{strategy_name}_c{child_size}_o{overlap}"
                                f"_h{'Y' if hybrid else 'N'}"
                                f"_m{'Y' if auto_merge else 'N'}"
                                f"_r{'Y' if rerank else 'N'}"
                            ),
                            chunking_strategy=strategy_name,
                            chunk_size_parent=parent_size,
                            chunk_size_child=child_size,
                            chunk_overlap=overlap,
                            semantic_breakpoint_threshold=95,
                            semantic_buffer_size=1,
                            enable_hybrid=hybrid,
                            enable_auto_merge=auto_merge,
                            enable_rerank=rerank,
                            llm_provider=self.llm_provider,
                            llm_model=llm,
                            llm_temperature=self.llm_temperature,
                            embedding_provider=self.embedding_provider,
                            embedding_model=emb,
                            embedding_dim=self.embedding_dim,
                            reranker_provider=self.reranker_provider,
                            reranker_model=reranker,
                            qdrant_url=self.qdrant_url,
                            qdrant_path=self.qdrant_path,
                            retrieval_top_k=self.retrieval_top_k,
                            rerank_top_k=self.rerank_top_k,
                            dashscope_api_key=api_key,
                        ))

        return configs

    @classmethod
    def from_yaml(cls, path: str) -> "ExperimentGrid":
        """从消融矩阵 YAML 文件加载。"""
        config_path = Path(path).resolve()
        if not config_path.exists():
            raise FileNotFoundError(f"消融配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        strategies_data = data.get("strategies", {})
        retrieval_data = data.get("retrieval", {})
        defaults_data = data.get("defaults", {})

        strategies: Dict[str, StrategyParams] = {}
        for name, params_dict in strategies_data.items():
            strategies[name] = StrategyParams(
                chunk_sizes_child=params_dict.get("chunk_sizes_child", [256]),
                chunk_overlaps=params_dict.get("chunk_overlaps", [50]),
                breakpoint_thresholds=params_dict.get("breakpoint_thresholds", [95]),
                buffer_sizes=params_dict.get("buffer_sizes", [1]),
            )

        kwargs: Dict[str, Any] = {}
        if strategies:
            kwargs["strategies"] = strategies

        if "enable_hybrid" in retrieval_data:
            kwargs["enable_hybrid"] = retrieval_data["enable_hybrid"]
        if "enable_auto_merge" in retrieval_data:
            kwargs["enable_auto_merge"] = retrieval_data["enable_auto_merge"]
        if "enable_rerank" in retrieval_data:
            kwargs["enable_rerank"] = retrieval_data["enable_rerank"]

        for key in [
            "chunk_sizes_parent", "llm_provider", "embedding_provider",
            "reranker_provider", "embedding_dim", "llm_temperature",
            "qdrant_url", "qdrant_path", "retrieval_top_k", "rerank_top_k",
            "llm_models", "embedding_models", "reranker_models",
        ]:
            if key in defaults_data:
                kwargs[key] = defaults_data[key]

        return cls(**kwargs)
