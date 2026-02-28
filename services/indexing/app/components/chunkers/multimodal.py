"""多模态切分器（图文对切分）。

功能：
- 按页或按图文区域切分
- 生成父节点（完整图文对，存 MySQL）
- 生成子节点（图像摘要文本节点，存 Qdrant）
- 建立父子关系
- 使用 VLM 为图片生成详细摘要
"""

import base64
from typing import List, Tuple, Dict, Any, Optional
from llama_index.core.schema import TextNode, IndexNode, NodeRelationship

from app.core.registry import ComponentRegistry
from app.core.types import BaseChunker, ImageType
from app.utils.logger import get_logger

logger = get_logger(__name__)


@ComponentRegistry.chunker("multimodal")
class MultimodalChunker(BaseChunker):
    """多模态切分策略：按页切分图文对，使用 VLM 生成图像摘要。

    返回值：tuple (parent_nodes, child_nodes)
    - parent_nodes: 包含完整图文对的父节点（存 MySQL）
    - child_nodes: 图像摘要文本节点（存 Qdrant，用于检索）
    """

    def create_splitter(self, chunk_size: int, chunk_overlap: int, **kwargs):
        """创建多模态切分器。

        Args:
            chunk_size: 未使用（多模态按页切分）。
            chunk_overlap: 未使用。
            **kwargs: 额外参数（api_key, vlm_model, enable_vlm_summary）。

        Returns:
            MultimodalSplitter 实例。
        """
        api_key = kwargs.get("api_key")
        vlm_model = kwargs.get("vlm_model", "qwen-vl-max")
        enable_vlm_summary = kwargs.get("enable_vlm_summary", True)

        return MultimodalSplitter(
            api_key=api_key,
            vlm_model=vlm_model,
            enable_vlm_summary=enable_vlm_summary
        )


class MultimodalSplitter:
    """多模态切分器实现。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        vlm_model: str = "qwen-vl-max",
        enable_vlm_summary: bool = True
    ):
        """初始化切分器。

        Args:
            api_key: DashScope API Key（用于 VLM 调用）。
            vlm_model: VLM 模型名称。
            enable_vlm_summary: 是否启用 VLM 摘要生成。
        """
        self.enable_vlm_summary = enable_vlm_summary
        self.vlm_provider = None

        if enable_vlm_summary and api_key:
            try:
                provider_class = ComponentRegistry.get_vlm_provider("dashscope")
                self.vlm_provider = provider_class(
                    api_key=api_key,
                    model_name=vlm_model
                )
                logger.info(f"VLM Provider 初始化成功: {vlm_model}")
            except Exception as e:
                logger.warning(f"VLM Provider 初始化失败: {e}，将使用简短描述")
                self.enable_vlm_summary = False

    def get_nodes_from_documents(
        self, documents: List[Any]
    ) -> Tuple[List[TextNode], List[IndexNode]]:
        """从 Documents 生成父子节点。

        Documents 的 metadata 应包含 multimodal_chunks 字段：
        [
            {
                "page": 1,
                "text": "...",
                "images": [
                    {
                        "data": bytes,
                        "bbox": ...,
                        "format": "jpeg",
                        "image_type": ImageType.SCREENSHOT,
                        "surrounding_text": "..."
                    }
                ],
                "role": "teacher"
            }
        ]

        Returns:
            tuple: (parent_nodes, child_nodes)
        """
        all_parent_nodes = []
        all_child_nodes = []

        for doc in documents:
            multimodal_chunks = doc.metadata.get("multimodal_chunks", [])

            if not multimodal_chunks:
                logger.warning(
                    f"文档 {doc.metadata.get('file_name', 'unknown')} "
                    "未包含 multimodal_chunks，跳过"
                )
                continue

            file_name = doc.metadata.get("file_name", "unknown")
            role = doc.metadata.get("role", "common")

            for chunk in multimodal_chunks:
                page = chunk["page"]
                text = chunk["text"]
                images = chunk["images"]
                chunk_role = chunk.get("role", role)

                # 跳过没有图片的页面
                if not images:
                    logger.debug(f"{file_name} 第 {page} 页无图片，跳过")
                    continue

                # 为每张图片生成摘要（如果启用 VLM）
                image_summaries = []
                for img_idx, img_data in enumerate(images):
                    summary = self._generate_image_summary(
                        img_data, file_name, page, img_idx
                    )
                    image_summaries.append(summary)

                # 创建父节点（包含完整图文对 + 摘要备份）
                parent_node = TextNode(
                    text=text,
                    metadata={
                        "file_name": file_name,
                        "page": page,
                        "role": chunk_role,
                        "node_type": "multimodal",
                        "node_format": "mixed",  # text + image
                        "image_count": len(images),
                        "images": self._serialize_images(images),  # 序列化图片
                        "image_summaries": image_summaries,  # 摘要备份
                    },
                )

                all_parent_nodes.append(parent_node)

                # 为每张图片创建子节点（用于向量检索）
                for img_idx, (img_data, summary) in enumerate(zip(images, image_summaries)):
                    # Child Node 的 text 字段存储完整摘要（用于检索）
                    child_text = f"[图像摘要] {summary}"

                    child_node = IndexNode(
                        text=child_text,
                        index_id=parent_node.id_,  # 指向父节点
                        metadata={
                            "file_name": file_name,
                            "page": page,
                            "role": chunk_role,
                            "node_type": "image_summary",
                            "image_index": img_idx,
                            "parent_id": parent_node.id_,
                            "image_type": img_data.get("image_type", ImageType.OTHER).value,
                            "image_format": img_data.get("format", "jpeg"),
                            "image_width": img_data.get("width", 0),
                            "image_height": img_data.get("height", 0),
                        },
                    )

                    # 建立父子关系
                    child_node.relationships[
                        NodeRelationship.PARENT
                    ] = parent_node.as_related_node_info()

                    all_child_nodes.append(child_node)

        logger.info(
            f"多模态切分完成: {len(all_parent_nodes)} 个父节点, "
            f"{len(all_child_nodes)} 个子节点（图像摘要）"
        )

        return all_parent_nodes, all_child_nodes

    def _generate_image_summary(
        self,
        img_data: Dict[str, Any],
        file_name: str,
        page: int,
        img_idx: int
    ) -> str:
        """为图片生成摘要。

        Args:
            img_data: 图片数据（包含 data, image_type, surrounding_text）
            file_name: 文件名
            page: 页码
            img_idx: 图片索引

        Returns:
            图片摘要文本
        """
        if not self.enable_vlm_summary or not self.vlm_provider:
            # 降级：使用简短描述
            return f"{file_name} 第 {page} 页图片 {img_idx + 1}"

        try:
            image_bytes = img_data["data"]
            image_type = img_data.get("image_type", ImageType.OTHER)
            surrounding_text = img_data.get("surrounding_text", "")

            # 调用 VLM 生成摘要
            summary = self.vlm_provider.generate_image_summary(
                image_bytes=image_bytes,
                image_type=image_type,
                surrounding_text=surrounding_text,
                temperature=0.1
            )

            logger.debug(
                f"图像摘要生成成功: {file_name} 第 {page} 页图片 {img_idx + 1}, "
                f"类型: {image_type.value}, 摘要长度: {len(summary)}"
            )

            return summary

        except Exception as e:
            logger.error(
                f"图像摘要生成失败: {file_name} 第 {page} 页图片 {img_idx + 1}, "
                f"错误: {e}，使用降级描述"
            )
            # 降级：使用简短描述
            return f"{file_name} 第 {page} 页图片 {img_idx + 1}"

    def _serialize_images(self, images: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """序列化图片为 base64（存储到 MySQL metadata）。

        Args:
            images: 图片数据列表（包含 bytes）。

        Returns:
            序列化后的图片列表（bytes -> base64）。
        """
        serialized = []
        for img in images:
            serialized.append({
                "base64": base64.b64encode(img["data"]).decode("utf-8"),
                "format": img.get("format", "jpeg"),
                "width": img.get("width", 0),
                "height": img.get("height", 0),
                "bbox": img.get("bbox"),
            })
        return serialized
