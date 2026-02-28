"""默认图像处理器。

使用 PIL/Pillow 进行图像压缩、格式转换、尺寸标准化。
"""

import hashlib
import io
from typing import Optional

try:
    from PIL import Image
except ImportError:
    raise ImportError(
        "Pillow is required for image processing. "
        "Install: pip install pillow"
    )

from app.core.registry import ComponentRegistry
from app.core.types import BaseImageProcessor
from app.utils.logger import get_logger

logger = get_logger(__name__)


@ComponentRegistry.image_processor("default")
class DefaultImageProcessor(BaseImageProcessor):
    """默认图像处理器：压缩、裁剪、格式转换、Hash 计算。"""

    def preprocess(
        self,
        image_bytes: bytes,
        max_size: int = 1024,
        quality: int = 85,
        output_format: str = "JPEG",
    ) -> bytes:
        """预处理图像。

        Args:
            image_bytes: 原始图像二进制数据。
            max_size: 最大边长（像素），超过则等比缩放。
            quality: JPEG 压缩质量（1-100）。
            output_format: 输出格式（JPEG/PNG）。

        Returns:
            处理后的图像二进制数据。
        """
        try:
            # 打开图像
            img = Image.open(io.BytesIO(image_bytes))

            # 转换为 RGB（JPEG 不支持透明通道）
            if img.mode in ("RGBA", "P"):
                # 创建白色背景
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "RGBA":
                    background.paste(img, mask=img.split()[3])  # 使用 alpha 通道作为 mask
                else:
                    background.paste(img)
                img = background
            elif img.mode != "RGB":
                img = img.convert("RGB")

            # 等比缩放
            width, height = img.size
            if max(width, height) > max_size:
                ratio = max_size / max(width, height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.debug(f"图像缩放: {width}x{height} -> {new_width}x{new_height}")

            # 保存到内存
            output = io.BytesIO()
            img.save(output, format=output_format, quality=quality, optimize=True)
            processed_bytes = output.getvalue()

            logger.debug(
                f"图像处理完成: 原始 {len(image_bytes)} bytes -> "
                f"处理后 {len(processed_bytes)} bytes "
                f"(压缩率 {len(processed_bytes) / len(image_bytes) * 100:.1f}%)"
            )

            return processed_bytes

        except Exception as e:
            logger.error(f"图像处理失败: {e}")
            # 失败时返回原始数据
            return image_bytes

    def extract_hash(self, image_bytes: bytes) -> str:
        """计算图像内容 MD5 hash（用于去重）。

        Args:
            image_bytes: 图像二进制数据。

        Returns:
            MD5 hash 字符串（32 位十六进制）。
        """
        return hashlib.md5(image_bytes).hexdigest()

    def get_image_dimensions(self, image_bytes: bytes) -> tuple[int, int]:
        """获取图像尺寸。

        Args:
            image_bytes: 图像二进制数据。

        Returns:
            (width, height) 元组。
        """
        try:
            img = Image.open(io.BytesIO(image_bytes))
            return img.size
        except Exception as e:
            logger.error(f"获取图像尺寸失败: {e}")
            return (0, 0)
