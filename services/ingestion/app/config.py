"""Ingestion 服务级配置。"""

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings


class ServiceSettings(BaseSettings):
    """Ingestion 服务配置，从环境变量加载。"""

    # Qdrant
    qdrant_url: str = "http://localhost:6333"

    # 服务端口
    host: str = "0.0.0.0"
    port: int = 8001

    # 文件存储（旧版，保留兼容）
    upload_dir: str = "data/uploads/documents"
    metadata_db_path: str = "data/metadata.db"

    # MinerU
    mineru_output_dir: str = "data/mineru_output"

    # DashScope
    dashscope_api_key: str = ""

    # ── 数据分区路径（新版，双轨制清洗） ──
    # 输入路径
    policy_data_dir: Path = Field(
        default=Path("data/policy"),
        description="政策与指标类文件存储目录"
    )
    manual_data_dir: Path = Field(
        default=Path("data/manual"),
        description="系统操作手册类文件存储目录"
    )

    # 输出路径
    parsed_output_dir: Path = Field(
        default=Path("data/parsed"),
        description="清洗产物根目录"
    )

    def get_parsed_dir(self, category: str, stage: str) -> Path:
        """获取清洗产物路径

        Args:
            category: 'policy' or 'manual'
            stage: 'raw' or 'cleaned'

        Returns:
            Path: data/parsed/{category}/{stage}/
        """
        return self.parsed_output_dir / category / stage

    model_config = {"env_prefix": "", "env_file": ".env"}


service_settings = ServiceSettings()
