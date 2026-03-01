"""PDF 解析器（使用 pymupdf4llm，专为 LLM 优化）。"""

from pathlib import Path
from typing import Dict, Any
import tempfile


class MinerUParser:
    """PDF->Markdown 解析器封装（使用 pymupdf4llm）。"""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._ready = self._check_parser_available()

    def _check_parser_available(self) -> bool:
        try:
            import pymupdf4llm  # noqa: F401
            return True
        except ImportError:
            return False

    def is_ready(self) -> bool:
        return self._ready

    def parse(self, pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
        """核心解析：PDF bytes -> {"filename", "markdown", "pages"}"""
        if not self._ready:
            raise RuntimeError("pymupdf4llm 未安装或未正确配置。")

        # 写入临时文件（pymupdf4llm 需要文件路径）
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_pdf = tmp_path / filename
            input_pdf.write_bytes(pdf_bytes)

            markdown_content, pages = self._parse_with_pymupdf4llm(input_pdf)
            return {
                "filename": filename,
                "markdown": markdown_content,
                "pages": pages,
            }

    def parse_file(self, pdf_path: Path) -> Dict[str, Any]:
        """从文件路径解析 PDF"""
        if not self._ready:
            raise RuntimeError("pymupdf4llm 未安装或未正确配置。")

        markdown_content, pages = self._parse_with_pymupdf4llm(pdf_path)
        return {
            "filename": pdf_path.name,
            "markdown": markdown_content,
            "pages": pages,
        }

    def parse_page_chunks(self, pdf_bytes: bytes, filename: str) -> list[dict]:
        """PDF → 逐页 Markdown 列表。

        Args:
            pdf_bytes: PDF 文件二进制数据。
            filename: 文件名。

        Returns:
            [{"page": 1, "text": "..."}, {"page": 2, "text": "..."}, ...]
        """
        if not self._ready:
            raise RuntimeError("pymupdf4llm 未安装或未正确配置。")

        import pymupdf4llm

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / filename
            tmp_path.write_bytes(pdf_bytes)

            chunks = pymupdf4llm.to_markdown(
                str(tmp_path),
                page_chunks=True,
                write_images=False,
            )

        if not isinstance(chunks, list):
            raise ValueError(f"pymupdf4llm 返回了非预期格式: {type(chunks)}")

        result = []
        for idx, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                continue
            metadata = chunk.get("metadata", {})
            page_num = metadata.get("page", idx + 1)
            result.append({
                "page": page_num,
                "text": chunk.get("text", ""),
            })

        return result

    def _parse_with_pymupdf4llm(self, pdf_path: Path) -> tuple[str, int]:
        """使用 pymupdf4llm 解析 PDF"""
        import pymupdf4llm

        # 解析为 Markdown
        md_content = pymupdf4llm.to_markdown(
            str(pdf_path),
            page_chunks=False,  # 不按页分块，返回完整文档
            write_images=False,  # 不提取图片（暂时）
        )

        # 估算页数（pymupdf4llm 不直接返回页数）
        import pymupdf
        doc = pymupdf.open(pdf_path)
        pages = len(doc)
        doc.close()

        return md_content, pages


def parse_document(file_path: str) -> list:
    """解析文档文件，返回 LlamaIndex Document 列表。

    包装 MinerUParser，供 ingest_from_bytes 调用。

    Args:
        file_path: PDF 文件路径。

    Returns:
        LlamaIndex Document 列表。
    """
    from llama_index.core import Document

    path = Path(file_path)
    parser = MinerUParser(output_dir=str(path.parent))
    result = parser.parse(path.read_bytes(), path.name)

    return [Document(
        text=result["markdown"],
        metadata={"file_name": path.name, "pages": result["pages"]},
    )]
