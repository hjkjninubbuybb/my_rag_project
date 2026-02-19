import os
import yaml
import sys
from typing import Optional, Set
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# 🛡️ 定义合法的切片策略白名单
VALID_STRATEGIES: Set[str] = {"fixed", "recursive", "sentence"}


class Settings(BaseSettings):
    # === 1. 系统与敏感配置 (来自 .env) ===
    app_name: str = "Agentic RAG"
    debug: bool = True
    # 敏感信息通过环境变量加载，不走 YAML
    dashscope_api_key: Optional[str] = None

    # === 2. 实验可变参数 (默认值作为兜底) ===

    # [Provider Group] — 供应商名称（对应 ComponentRegistry 注册的 key）
    llm_provider: str = "dashscope"
    embedding_provider: str = "dashscope"
    reranker_provider: str = "dashscope"

    # [Model Group]
    llm_model: str = "qwen-plus"
    llm_temperature: float = 0.1
    embedding_model: str = "text-embedding-v4"
    embedding_dim: int = 1536
    reranker_model: str = "gte-rerank"

    # [Storage Group]
    qdrant_path: str = "data/vectordb"
    metadata_db_path: str = "data/metadata.db"
    collection_name: str = "my_rag_collection"

    # [RAG Strategy Group]
    chunking_strategy: str = "fixed"
    chunk_size_parent: int = 1024
    chunk_size_child: int = 256
    chunk_overlap: int = 50
    retrieval_top_k: int = 50
    rerank_top_k: int = 5

    # [Retrieval Pipeline Switches]
    enable_hybrid: bool = True
    enable_auto_merge: bool = True
    enable_rerank: bool = True

    # [Meta Group]
    experiment_id: str = "default"
    experiment_description: str = "Default Configuration"

    # Pydantic 配置
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def to_experiment_config(self):
        """桥梁方法: 将全局 Settings 转为不可变 ExperimentConfig。

        便于从旧代码平滑过渡到基于 config 的依赖注入。
        """
        from rag.config.experiment import ExperimentConfig

        return ExperimentConfig(
            experiment_id=self.experiment_id,
            experiment_description=self.experiment_description,
            llm_provider=self.llm_provider,
            llm_model=self.llm_model,
            llm_temperature=self.llm_temperature,
            embedding_provider=self.embedding_provider,
            embedding_model=self.embedding_model,
            embedding_dim=self.embedding_dim,
            reranker_provider=self.reranker_provider,
            reranker_model=self.reranker_model,
            qdrant_path=self.qdrant_path,
            collection_name_override=self.collection_name,
            chunking_strategy=self.chunking_strategy,
            chunk_size_parent=self.chunk_size_parent,
            chunk_size_child=self.chunk_size_child,
            chunk_overlap=self.chunk_overlap,
            enable_hybrid=self.enable_hybrid,
            enable_auto_merge=self.enable_auto_merge,
            enable_rerank=self.enable_rerank,
            retrieval_top_k=self.retrieval_top_k,
            rerank_top_k=self.rerank_top_k,
            dashscope_api_key=self.dashscope_api_key or "",
        )

    def load_experiment_config(self, config_path: str):
        """
        [核心] 安全加载 YAML 配置文件并覆盖当前设置
        包含路径检查和策略合法性校验。
        """
        # 1. 路径安全检查
        path = Path(config_path).resolve()

        if not path.exists():
            # 🔴 Fatal Error: 如果指定了配置却找不到，必须报错停止
            error_msg = f"❌ [Fatal] 配置文件不存在: {path}\n请检查路径是否正确，或确保在项目根目录下运行。"
            print(error_msg)
            # 直接抛出异常，中断程序启动
            raise FileNotFoundError(error_msg)

        print(f"⚙️ [Config] 正在加载实验配置: {path.name}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)

            # 2. 逐层解析 YAML 并覆盖 Settings 属性
            # 使用 .get() 安全读取，只覆盖 YAML 中存在的字段

            # --- Experiment Group ---
            if "experiment" in config_data:
                exp = config_data["experiment"]
                self.experiment_id = exp.get("id", self.experiment_id)
                self.experiment_description = exp.get("description", self.experiment_description)

            # --- Model Group ---
            if "model" in config_data:
                m = config_data["model"]
                self.llm_provider = m.get("llm_provider", self.llm_provider)
                self.llm_model = m.get("llm_model", self.llm_model)
                self.llm_temperature = m.get("llm_temperature", self.llm_temperature)
                self.embedding_provider = m.get("embedding_provider", self.embedding_provider)
                self.embedding_model = m.get("embedding_model", self.embedding_model)
                self.embedding_dim = m.get("embedding_dim", self.embedding_dim)
                self.reranker_provider = m.get("reranker_provider", self.reranker_provider)
                self.reranker_model = m.get("reranker_model", self.reranker_model)

            # --- Storage Group ---
            if "storage" in config_data:
                s = config_data["storage"]
                self.qdrant_path = s.get("qdrant_path", self.qdrant_path)
                self.collection_name = s.get("collection_name", self.collection_name)
                self.metadata_db_path = s.get("metadata_db_path", self.metadata_db_path)

            # --- RAG Strategy Group (核心) ---
            if "rag" in config_data:
                r = config_data["rag"]

                # 读取策略字符串
                strategy = r.get("chunking_strategy", self.chunking_strategy)

                # 🛡️ Safety Check: 策略合法性校验
                if strategy not in VALID_STRATEGIES:
                    error_msg = f"❌ [Config Error] 未知的切片策略: '{strategy}'\n合法值: {VALID_STRATEGIES}"
                    print(error_msg)
                    raise ValueError(error_msg)

                # 校验通过，赋值
                self.chunking_strategy = strategy

                # 读取数值参数
                self.chunk_size_parent = r.get("chunk_size_parent", self.chunk_size_parent)
                self.chunk_size_child = r.get("chunk_size_child", self.chunk_size_child)
                self.chunk_overlap = r.get("chunk_overlap", self.chunk_overlap)
                self.retrieval_top_k = r.get("retrieval_top_k", self.retrieval_top_k)
                self.rerank_top_k = r.get("rerank_top_k", self.rerank_top_k)

            # --- Retrieval Pipeline Group ---
            if "retrieval" in config_data:
                ret = config_data["retrieval"]
                self.enable_hybrid = ret.get("enable_hybrid", self.enable_hybrid)
                self.enable_auto_merge = ret.get("enable_auto_merge", self.enable_auto_merge)
                self.enable_rerank = ret.get("enable_rerank", self.enable_rerank)

            # 3. 打印成功日志
            print(f"✅ [Config] 加载完成 | 实验ID: {self.experiment_id}")
            print(f"   -> 集合: {self.collection_name}")
            print(
                f"   -> 策略: {self.chunking_strategy} (Size: {self.chunk_size_child}, Overlap: {self.chunk_overlap})")

        except Exception as e:
            print(f"❌ [Fatal] 解析配置文件失败: {e}")
            # 再次抛出异常，确保 Main 函数能捕获并退出
            raise e


# 初始化单例
settings = Settings()