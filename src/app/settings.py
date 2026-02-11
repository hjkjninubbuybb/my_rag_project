import os
import yaml
import sys
from typing import Optional, Set
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# 🛡️ [Security] 定义合法的切片策略白名单
# 新增 "semantic" 策略支持
VALID_STRATEGIES: Set[str] = {"fixed", "recursive", "sentence", "semantic"}


class Settings(BaseSettings):
    # === 1. 系统与敏感配置 (来自 .env) ===
    app_name: str = "Agentic RAG"
    debug: bool = True
    # 敏感信息通过环境变量加载，不走 YAML
    dashscope_api_key: Optional[str] = None

    # === 2. 实验可变参数 (默认值作为兜底) ===

    # [Model Group]
    llm_model: str = "qwen-plus"
    embedding_model: str = "text-embedding-v4"
    embedding_dim: int = 1536

    # [Storage Group]
    qdrant_path: str = "qdrant_db"
    collection_name: str = "my_rag_collection"

    # [RAG Strategy Group]
    chunking_strategy: str = "fixed"

    # 父文档块大小 (用于 Auto-Merging 的上下文窗口)
    chunk_size_parent: int = 1024
    # 子文档块/实际索引块大小 (基准切分大小)
    chunk_size_child: int = 256
    # 重叠窗口
    chunk_overlap: int = 50

    retrieval_top_k: int = 50
    rerank_top_k: int = 5

    # [Semantic Splitting Group] (新增 - 针对中文优化的参数)
    # 缓冲区大小 (Buffer Size):
    # 中文短句较多，设为 3 意味着算法会看前后各 3 个子句来平滑语义噪音。
    semantic_buffer_size: int = 3

    # 语义差异阈值 (Breakpoint Threshold):
    # 基于百分位 (Percentile)。因为我们按逗号切得很细，大部分相邻子句语义都连贯。
    # 设为 80 意味着忽略掉 80% 的微小波动，只在语义差异最大的 20% 处切分。
    semantic_breakpoint_threshold: int = 80

    # [Meta Group]
    experiment_id: str = "default"
    experiment_description: str = "Default Configuration"

    # Pydantic 配置
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
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
                self.llm_model = m.get("llm_model", self.llm_model)
                self.embedding_model = m.get("embedding_model", self.embedding_model)
                self.embedding_dim = m.get("embedding_dim", self.embedding_dim)

            # --- Storage Group ---
            if "storage" in config_data:
                s = config_data["storage"]
                self.qdrant_path = s.get("qdrant_path", self.qdrant_path)
                self.collection_name = s.get("collection_name", self.collection_name)

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

                # [Update] 读取语义分割参数
                self.semantic_buffer_size = r.get("semantic_buffer_size", self.semantic_buffer_size)
                self.semantic_breakpoint_threshold = r.get("semantic_breakpoint_threshold",
                                                           self.semantic_breakpoint_threshold)

            # 3. 打印成功日志
            print(f"✅ [Config] 加载完成 | 实验ID: {self.experiment_id}")
            print(f"   -> 集合: {self.collection_name}")
            print(
                f"   -> 策略: {self.chunking_strategy} (Size: {self.chunk_size_child}, Overlap: {self.chunk_overlap})")

            if self.chunking_strategy == "semantic":
                print(
                    f"   -> [Semantic] Buffer: {self.semantic_buffer_size}, Threshold: {self.semantic_breakpoint_threshold}")

        except Exception as e:
            print(f"❌ [Fatal] 解析配置文件失败: {e}")
            # 再次抛出异常，确保 Main 函数能捕获并退出
            raise e


# 初始化单例
settings = Settings()