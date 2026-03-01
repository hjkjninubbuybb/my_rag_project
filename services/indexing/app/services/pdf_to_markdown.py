"""PDF 转 Markdown 服务：图片以 base64 返回，Markdown 中通过相对路径引用。"""

import base64
import tempfile
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from app.parsing.parser import MinerUParser
from app.parsing.multimodal_parser import MultimodalPDFParser
from app.parsing.markdown_cleaner import MarkdownCleaner
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ConversionResult:
    """PDF→Markdown 转换结果。"""

    filename: str
    pages: int
    image_count: int
    images: list[dict] = field(default_factory=list)  # [{name, format, data_base64}]
    markdown_content: str = ""


class PDFToMarkdownService:
    """将 PDF 转为 Markdown，图片以 base64 返回。"""

    def __init__(self):
        self.text_parser = MinerUParser(output_dir=tempfile.gettempdir())
        self.image_parser = MultimodalPDFParser()
        self.cleaner = MarkdownCleaner()

    def convert(self, pdf_bytes: bytes, filename: str) -> ConversionResult:
        """将 PDF 转为带图片引用的 Markdown。

        流程：
        1. MultimodalPDFParser 提取逐页图片
        2. 收集图片为 base64
        3. MinerUParser 获取逐页 Markdown
        4. 按页码注入图片引用（相对路径）
        5. 返回 Markdown 内容 + 图片列表

        Args:
            pdf_bytes: PDF 文件二进制数据。
            filename: PDF 文件名。

        Returns:
            ConversionResult 包含转换结果。
        """
        stem = PurePosixPath(filename).stem

        # 1. 提取图片（逐页，含小图过滤和 MD5 去重）
        image_pages = self.image_parser.parse(pdf_bytes, filename)
        logger.info(f"提取图片完成: {len(image_pages)} 页")

        # 2. 收集图片，构建页码→图片引用映射
        page_image_refs: dict[int, list[str]] = {}
        all_images: list[dict] = []

        for page_data in image_pages:
            page_num = page_data["page"]
            for idx, img in enumerate(page_data["images"]):
                img_hash = img["hash"][:8]
                img_fmt = img["format"]
                image_name = f"{stem}/{page_num:04d}_{idx:02d}_{img_hash}.{img_fmt}"

                # Encode image data as base64
                img_b64 = base64.b64encode(img["data"]).decode("ascii")
                all_images.append({
                    "name": image_name,
                    "format": img_fmt,
                    "data_base64": img_b64,
                })

                # Use relative path in markdown
                ref_path = f"images/{page_num:04d}_{idx:02d}_{img_hash}.{img_fmt}"
                page_image_refs.setdefault(page_num, []).append(ref_path)

        logger.info(f"收集 {len(all_images)} 张图片")

        # 3. 获取逐页 Markdown
        page_chunks = self.text_parser.parse_page_chunks(pdf_bytes, filename)
        logger.info(f"解析 Markdown 完成: {len(page_chunks)} 页")

        # 4. 按页码注入图片引用
        md_parts: list[str] = []
        for chunk in page_chunks:
            page_num = chunk["page"]
            page_text = chunk["text"]

            # 在页面文本末尾追加图片引用
            refs = page_image_refs.get(page_num, [])
            if refs:
                ref_lines = "\n".join(
                    f"![img_{i}]({ref})" for i, ref in enumerate(refs)
                )
                page_text = f"{page_text}\n\n{ref_lines}"

            md_parts.append(page_text)

        full_markdown = "\n\n---\n\n".join(md_parts)

        # 4.5 清洗 Markdown（去除重复页眉、残留页码、目录、多余空行）
        full_markdown = self.cleaner.clean(full_markdown)
        logger.info("Markdown 清洗完成")

        return ConversionResult(
            filename=filename,
            pages=len(page_chunks),
            image_count=len(all_images),
            images=all_images,
            markdown_content=full_markdown,
        )
