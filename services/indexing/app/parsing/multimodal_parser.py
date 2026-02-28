"""多模态 PDF 解析器。

使用 PyMuPDF (fitz) 提取 PDF 中的图文对，建立文本和图像的对应关系。
"""

import io
from typing import List, Dict, Any
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    raise ImportError(
        "PyMuPDF is required for multimodal PDF parsing. "
        "Install: pip install pymupdf"
    )

from app.utils.role_mapper import extract_role_from_filename
from app.utils.logger import get_logger
from app.core.types import ImageType

logger = get_logger(__name__)


class MultimodalPDFParser:
    """多模态 PDF 解析器，提取图文对。"""

    def _is_toc_page(self, text: str) -> bool:
        """判断是否为目录页。

        检测规则（针对郑州大学手册格式）：
        1. 包含"目录"关键字
        2. 包含大量省略号（......）用于对齐页码

        Args:
            text: 页面文本

        Returns:
            True 如果是目录页
        """
        if not text:
            return False

        has_toc_keyword = "目录" in text or "目 录" in text
        dot_count = text.count(".")
        has_many_dots = dot_count > 20

        return has_toc_keyword and has_many_dots

    def _classify_image_type(
        self,
        image_info: Dict[str, Any],
        page_text: str
    ) -> ImageType:
        """基于启发式规则分类图片类型。

        Args:
            image_info: 图片信息（包含 width, height, bbox）
            page_text: 页面文本

        Returns:
            图片类型枚举
        """
        width = image_info.get("width", 0)
        height = image_info.get("height", 0)

        # 规则 1: 大尺寸横向图片 + 包含流程关键词 → 流程图
        if width > 600 and width > height * 1.2:
            flow_keywords = ["流程", "步骤", "审核", "申请", "提交", "审批"]
            if any(kw in page_text for kw in flow_keywords):
                return ImageType.FLOWCHART

        # 规则 2: 方形或竖向图片 + 包含表格关键词 → 表格
        if height >= width * 0.8:
            table_keywords = ["表", "学分", "成绩", "要求", "标准", "分数"]
            if any(kw in page_text for kw in table_keywords):
                return ImageType.TABLE

        # 规则 3: 大尺寸图片 + 包含系统/界面关键词 → 系统截图
        if width > 400 and height > 300:
            ui_keywords = ["界面", "系统", "登录", "点击", "按钮", "菜单", "操作"]
            if any(kw in page_text for kw in ui_keywords):
                return ImageType.SCREENSHOT

        # 规则 4: 包含图表关键词 → 图表
        diagram_keywords = ["图", "架构", "结构", "关系", "模型"]
        if any(kw in page_text for kw in diagram_keywords):
            return ImageType.DIAGRAM

        # 默认: 系统截图（教务手册中最常见）
        return ImageType.SCREENSHOT

    def _extract_surrounding_text(
        self,
        page_text: str,
        image_bbox: tuple,
        context_lines: int = 3
    ) -> str:
        """提取图片周围的文本作为上下文。

        Args:
            page_text: 页面完整文本
            image_bbox: 图片位置 (x0, y0, x1, y1)
            context_lines: 提取前后各几行文本

        Returns:
            周围文本（去重、清理后）
        """
        if not page_text or not image_bbox:
            return ""

        # 简单策略：取页面文本的前 N 行和后 N 行
        # （更精确的方法需要 OCR 坐标，这里用简化版本）
        lines = page_text.split("\n")
        lines = [line.strip() for line in lines if line.strip()]

        # 取前后各 context_lines 行
        if len(lines) <= context_lines * 2:
            surrounding = "\n".join(lines)
        else:
            # 取前 N 行和后 N 行
            before = lines[:context_lines]
            after = lines[-context_lines:]
            surrounding = "\n".join(before + after)

        # 清理：去除过长的行（可能是噪音）
        cleaned_lines = []
        for line in surrounding.split("\n"):
            if len(line) < 200:  # 过长的行可能是解析错误
                cleaned_lines.append(line)

        return "\n".join(cleaned_lines[:context_lines * 2])  # 最多保留 2*N 行

    def parse(self, pdf_bytes: bytes, filename: str) -> List[Dict[str, Any]]:
        """解析 PDF，提取每页的文本和图片。

        Args:
            pdf_bytes: PDF 文件的二进制数据。
            filename: 文件名（用于提取角色标识）。

        Returns:
            图文对列表，每个元素包含：
            {
                "page": int,  # 页码（从 1 开始）
                "text": str,  # 页面文本
                "images": [   # 图片列表
                    {
                        "data": bytes,  # 图片二进制数据
                        "bbox": (x0, y0, x1, y1),  # 位置信息
                        "format": str,  # 图片格式（png/jpeg）
                        "width": int,
                        "height": int
                    }
                ],
                "role": str  # 文档角色（从文件名提取）
            }
        """
        # 提取角色
        role = extract_role_from_filename(filename)
        logger.info(f"解析多模态 PDF: {filename}, 角色: {role}")

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        results = []

        try:
            for page_num in range(len(doc)):
                page = doc[page_num]

                # 提取文本
                text = page.get_text("text")

                # 提取图片
                images = []
                image_list = page.get_images(full=True)

                for img_info in enumerate(image_list):
                    xref = img_info[1][0]  # img_info is (index, img_data)

                    # 提取图片数据
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]

                    # 获取图片位置（bbox）
                    img_rects = page.get_image_rects(xref)
                    bbox = None
                    if img_rects:
                        rect = img_rects[0]  # 取第一个位置
                        bbox = (rect.x0, rect.y0, rect.x1, rect.y1)

                    # 获取图片尺寸
                    try:
                        from PIL import Image
                        img_pil = Image.open(io.BytesIO(image_bytes))
                        width, height = img_pil.size
                    except ImportError:
                        # 如果没有 PIL，使用默认值
                        width, height = 0, 0

                    # 构建图片信息字典
                    img_dict = {
                        "data": image_bytes,
                        "bbox": bbox,
                        "format": image_ext,
                        "width": width,
                        "height": height,
                    }

                    # 分类图片类型
                    image_type = self._classify_image_type(img_dict, text)
                    img_dict["image_type"] = image_type

                    # 提取周围文本
                    surrounding_text = self._extract_surrounding_text(text, bbox)
                    img_dict["surrounding_text"] = surrounding_text

                    images.append(img_dict)

                # 跳过目录页
                if self._is_toc_page(text):
                    logger.debug(f"跳过目录页: 第 {page_num + 1} 页")
                    continue

                results.append({
                    "page": page_num + 1,  # 页码从 1 开始
                    "text": text.strip(),
                    "images": images,
                    "role": role,
                })

        finally:
            doc.close()

        logger.info(
            f"解析完成: {len(results)} 页, "
            f"总图片数: {sum(len(r['images']) for r in results)}"
        )

        return results

    def parse_from_file(self, pdf_path: str) -> List[Dict[str, Any]]:
        """从文件路径解析 PDF。

        Args:
            pdf_path: PDF 文件路径。

        Returns:
            图文对列表。
        """
        path = Path(pdf_path)
        with open(path, "rb") as f:
            pdf_bytes = f.read()

        return self.parse(pdf_bytes, path.name)
