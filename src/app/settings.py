import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# 获取项目根目录 (my_rag_project/)
ROOT_DIR = Path(__file__).parent.parent.parent


class AppSettings(BaseSettings):
    """
    应用全局配置
    自动读取 .env 文件，或使用默认值
    """
    model_config = SettingsConfigDict(
        env_file=os.path.join(ROOT_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

    # --- 阿里云百炼 (DashScope) ---
    # 允许为空(Optional)，方便在没有 Key 的环境下跑单元测试
    dashscope_api_key: str | None = None

    llm_model: str = "qwen-plus-2025-12-01"
    embedding_model: str = "text-embedding-v4"

    # --- Qdrant 向量库 ---
    # 默认路径在项目根目录下的 qdrant_db
    qdrant_path: str = str(ROOT_DIR / "qdrant_db")
    qdrant_collection: str = "rag_collection"

    # --- 本地文档存储 (DocStore) ---
    # 这一步对于"父子索引"至关重要，用于存储父文档的完整内容
    storage_dir: str = str(ROOT_DIR / "storage_store")

    # --- 切片配置 (Chunking) ---
    # 父块大小: 1024 tokens (提供丰富上下文)
    chunk_size_parent: int = 1024
    # 子块大小: 256 tokens (提供精准检索)
    chunk_size_child: int = 256
    chunk_overlap: int = 20


# 单例导出
settings = AppSettings()

# 自动创建必要的目录 (如果不是内存模式)
if settings.qdrant_path != ":memory:":
    Path(settings.qdrant_path).mkdir(parents=True, exist_ok=True)

if settings.storage_dir != ":memory:":
    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)