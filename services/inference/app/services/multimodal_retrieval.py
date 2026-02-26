"""多模态检索服务。

专门处理图像向量检索（使用 Qdrant Named Vectors）。
"""

import base64
import tempfile
from typing import List, Dict, Any, Optional
from pathlib import Path

from qdrant_client import models
from sqlalchemy import create_engine, text

from rag_shared.config.experiment import ExperimentConfig
from rag_shared.core.registry import ComponentRegistry
from rag_shared.utils.logger import get_logger

from app.storage.vectordb import VectorStoreManager

logger = get_logger(__name__)


class MultimodalRetrievalService:
    """多模态检索服务 — 图像向量检索 + 父节点召回。"""

    def __init__(self, config: ExperimentConfig):
        """初始化服务。

        Args:
            config: 实验配置（必须启用 enable_multimodal）。
        """
        self.config = config
        self.store_manager = VectorStoreManager(config)

        # 多模态 Embedding Provider
        if config.enable_multimodal:
            mm_provider_class = ComponentRegistry.get_multimodal_embedding_provider(
                config.multimodal_embedding_provider
            )
            self.mm_embed_provider = mm_provider_class(
                api_key=config.dashscope_api_key
            )
        else:
            self.mm_embed_provider = None

        logger.info(f"MultimodalRetrievalService 初始化: collection={config.collection_name}")

    def search_by_image(
        self,
        image_bytes: bytes,
        top_k: int = 5,
        user_role: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """纯图像检索（多模态查询专用）。

        Args:
            image_bytes: 用户上传的截图（二进制数据）。
            top_k: 返回结果数量。
            user_role: 用户角色（用于过滤，如 "teacher"）。

        Returns:
            检索结果列表，每个元素包含：
            {
                "text": str,  # 父节点文本
                "score": float,  # 相似度分数
                "metadata": dict,  # 元数据（包含图片 base64）
                "source_file": str,
                "page": int,
                "role": str,
            }
        """
        if not self.mm_embed_provider:
            raise RuntimeError("多模态 embedding provider 未初始化")

        logger.info(f"开始图像检索: top_k={top_k}, user_role={user_role}")

        # 1. 生成图像 embedding（需要临时保存文件）
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False, mode="wb") as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            query_vector = self.mm_embed_provider.embed_images([tmp_path])[0]  # 2560 维
            logger.debug(f"查询向量生成完成: {len(query_vector)} 维")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        # 2. Qdrant 检索（使用 image named vector）
        # 构建过滤条件
        filter_conditions = []
        if user_role:
            filter_conditions.append(
                models.FieldCondition(
                    key="role",
                    match=models.MatchValue(value=user_role),
                )
            )

        query_filter = None
        if filter_conditions:
            query_filter = models.Filter(must=filter_conditions)

        search_results = self.store_manager.client.query_points(
            collection_name=self.config.collection_name,
            query=query_vector,
            using="image",  # ⚠️ 关键：指定使用图像向量
            query_filter=query_filter,
            limit=top_k,
        ).points

        logger.info(f"Qdrant 检索完成: 返回 {len(search_results)} 个结果")

        # 3. 递归召回父节点（从 MySQL）
        results = self._fetch_parents_from_results(search_results)

        logger.info(f"父节点召回完成: {len(results)} 个结果")
        return results

    def _fetch_parents_from_results(
        self, search_results: List[Any]
    ) -> List[Dict[str, Any]]:
        """从 Qdrant 检索结果召回 MySQL 父节点。

        Args:
            search_results: Qdrant 返回的 ScoredPoint 列表。

        Returns:
            包含父节点完整内容的结果列表。
        """
        parent_ids = [r.payload.get("parent_id") for r in search_results if r.payload.get("parent_id")]

        if not parent_ids:
            logger.warning("检索结果中未找到 parent_id，返回空列表")
            return []

        # 从 MySQL 查询父节点
        try:
            engine = create_engine(self.config.mysql_url)

            with engine.connect() as conn:
                # 构建 IN 查询
                placeholders = ", ".join([f":id{i}" for i in range(len(parent_ids))])
                sql = text(f"""
                    SELECT id, file_name, text, metadata
                    FROM parent_nodes
                    WHERE collection_name = :collection_name
                    AND id IN ({placeholders})
                """)

                params = {"collection_name": self.config.collection_name}
                for i, pid in enumerate(parent_ids):
                    params[f"id{i}"] = pid

                result = conn.execute(sql, params)
                parent_rows = {row[0]: row for row in result}  # id -> row

            engine.dispose()

        except Exception as e:
            logger.error(f"查询 MySQL 父节点失败: {e}")
            return []

        # 组装结果
        final_results = []
        for i, scored_point in enumerate(search_results):
            parent_id = scored_point.payload.get("parent_id")
            if not parent_id or parent_id not in parent_rows:
                continue

            parent_row = parent_rows[parent_id]
            import json

            metadata = json.loads(parent_row[3]) if parent_row[3] else {}

            final_results.append({
                "text": parent_row[2],  # text 字段
                "score": scored_point.score,
                "metadata": metadata,
                "source_file": parent_row[1],  # file_name
                "page": metadata.get("page", 0),
                "role": metadata.get("role", "common"),
            })

        return final_results
