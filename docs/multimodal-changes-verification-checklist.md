# 多模态架构变更验证清单

## 文档说明

本文档记录了多模态架构实施的所有代码变更，按照实施顺序（Phase 1 → Phase 2 → Phase 3）组织，每个变更包含：
- 文件路径
- 变更类型（新增/修改）
- 具体变更内容
- 验证方法
- 预期结果

## 验证环境准备

### 前置条件
```bash
# 1. 确保所有服务的依赖已安装
cd shared && poetry install
cd ../services/ingestion && poetry install
cd ../services/inference && poetry install
cd ../services/gateway && poetry install

# 2. 确保 Qdrant 运行
docker run -d -p 6333:6333 qdrant/qdrant

# 3. 确保 MySQL 运行并执行迁移脚本
mysql -u rag_user -p rag_db < scripts/migrate_multimodal_schema.sql

# 4. 设置环境变量
export DASHSCOPE_API_KEY="your_api_key"
```

---

## Phase 1: 基础设施（VLM Provider + 类型定义）

### 变更 1.1: 添加 ImageType 枚举和 BaseVLMProvider 接口

**文件**: `shared/rag_shared/core/types.py`

**变更类型**: 修改（扩展）

**具体变更**:
```python
# 1. 在文件开头添加导入
from enum import Enum
from typing import Any, List, Dict, Optional  # 添加 Dict, Optional

# 2. 在 BaseChunker 之前添加枚举类型部分
# ──────────────────── 枚举类型 ────────────────────

class ImageType(str, Enum):
    """图片类型枚举（用于多模态解析）。"""
    SCREENSHOT = "screenshot"      # 系统截图（界面元素、按钮）
    FLOWCHART = "flowchart"        # 流程图（审批流程、操作步骤）
    TABLE = "table"                # 表格截图（学分表、数据统计）
    DIAGRAM = "diagram"            # 其他图表（架构图、关系图）
    OTHER = "other"                # 未分类图片

# 3. 在文件末尾（BaseImageProcessor 之后）添加 VLM Provider 接口
class BaseVLMProvider(ABC):
    """视觉语言模型（VLM）供应商接口。

    用于图像摘要生成和多模态推理。
    """

    @abstractmethod
    def generate_image_summary(
        self,
        image_bytes: bytes,
        image_type: ImageType,
        surrounding_text: Optional[str] = None,
        **kwargs
    ) -> str:
        """为图片生成详细的文本摘要。

        Args:
            image_bytes: 图像二进制数据。
            image_type: 图片类型（用于选择合适的 prompt）。
            surrounding_text: 图片周围的文本（提供上下文）。
            **kwargs: 额外参数（如 temperature, max_tokens）。

        Returns:
            详细的文本摘要，包含所有关键专业名词。
        """
        ...

    @abstractmethod
    def generate_with_images(
        self,
        query: str,
        text_context: str,
        images: List[bytes],
        **kwargs
    ) -> str:
        """基于文本上下文和图片生成答案。

        Args:
            query: 用户问题。
            text_context: 检索到的文本上下文。
            images: 图片二进制数据列表。
            **kwargs: 额外参数（如 temperature）。

        Returns:
            生成的答案文本。
        """
        ...
```

**验证方法**:
```bash
cd shared
poetry run python -c "
from rag_shared.core.types import ImageType, BaseVLMProvider
print('ImageType values:', [t.value for t in ImageType])
print('BaseVLMProvider methods:', [m for m in dir(BaseVLMProvider) if not m.startswith('_')])
"
```

**预期结果**:
```
ImageType values: ['screenshot', 'flowchart', 'table', 'diagram', 'other']
BaseVLMProvider methods: ['generate_image_summary', 'generate_with_images']
```

---

### 变更 1.2: 添加 VLM Provider 注册支持

**文件**: `shared/rag_shared/core/registry.py`

**变更类型**: 修改（扩展）

**具体变更**:
```python
# 1. 在导入部分添加 BaseVLMProvider
from rag_shared.core.types import (
    BaseChunker,
    BaseLLMProvider,
    BaseEmbeddingProvider,
    BaseRerankerProvider,
    BaseMultimodalEmbeddingProvider,
    BaseMultimodalLLMProvider,
    BaseImageProcessor,
    BaseVLMProvider,  # 新增
)

# 2. 在 ComponentRegistry 类中添加注册表
class ComponentRegistry:
    """全局组件注册中心。所有组件通过装饰器自注册。"""

    _chunkers: dict[str, Type[BaseChunker]] = {}
    _llm_providers: dict[str, Type[BaseLLMProvider]] = {}
    _embedding_providers: dict[str, Type[BaseEmbeddingProvider]] = {}
    _reranker_providers: dict[str, Type[BaseRerankerProvider]] = {}
    _multimodal_embedding_providers: dict[str, Type[BaseMultimodalEmbeddingProvider]] = {}
    _multimodal_llm_providers: dict[str, Type[BaseMultimodalLLMProvider]] = {}
    _image_processors: dict[str, Type[BaseImageProcessor]] = {}
    _vlm_providers: dict[str, Type[BaseVLMProvider]] = {}  # 新增

# 3. 在文件末尾（get_image_processor 之后）添加 VLM Provider 方法
    # --- VLM 供应商 ---

    @classmethod
    def vlm_provider(cls, name: str):
        """装饰器: 注册 VLM 供应商。"""
        def decorator(klass: Type[BaseVLMProvider]):
            cls._vlm_providers[name] = klass
            return klass
        return decorator

    @classmethod
    def get_vlm_provider(cls, name: str) -> Type[BaseVLMProvider]:
        if name not in cls._vlm_providers:
            available = list(cls._vlm_providers.keys())
            raise ValueError(
                f"Unknown VLM provider '{name}'. Available: {available}"
            )
        return cls._vlm_providers[name]
```

**验证方法**:
```bash
cd shared
poetry run python -c "
from rag_shared.core.registry import ComponentRegistry
print('VLM provider methods exist:', hasattr(ComponentRegistry, 'vlm_provider'))
print('Get VLM provider method exists:', hasattr(ComponentRegistry, 'get_vlm_provider'))
"
```

**预期结果**:
```
VLM provider methods exist: True
Get VLM provider method exists: True
```

---

### 变更 1.3: 创建 DashScope VLM Provider

**文件**: `services/ingestion/app/components/providers/vlm.py`

**变更类型**: 新增

**具体变更**: 创建完整的 VLM Provider 实现（约 250 行）

**关键功能**:
1. `generate_image_summary()`: 为图片生成详细摘要
2. `generate_with_images()`: 多模态生成（图文混合）
3. `_build_summary_prompt()`: 针对不同图片类型的 prompt
4. `_build_generation_prompt()`: 多模态生成的 prompt

**验证方法**:
```bash
cd services/ingestion
poetry run python -c "
from rag_shared.core.registry import ComponentRegistry
import app.components.providers.vlm

# 检查是否注册成功
provider_class = ComponentRegistry.get_vlm_provider('dashscope')
print('Provider class:', provider_class.__name__)
print('Provider methods:', [m for m in dir(provider_class) if not m.startswith('_')])
"
```

**预期结果**:
```
Provider class: DashScopeVLMProvider
Provider methods: ['API_URL', 'generate_image_summary', 'generate_with_images']
```

---

### 变更 1.4: 注册 VLM Provider（Ingestion）

**文件**: `services/ingestion/app/components/providers/__init__.py`

**变更类型**: 修改

**具体变更**:
```python
"""Ingestion 服务 Provider 自注册。"""

import app.components.providers.dashscope  # noqa: F401
import app.components.providers.bgem3  # noqa: F401
import app.components.providers.vlm  # noqa: F401  # 新增
```

**验证方法**:
```bash
cd services/ingestion
poetry run python -c "
import app.components.providers
from rag_shared.core.registry import ComponentRegistry
providers = list(ComponentRegistry._vlm_providers.keys())
print('Registered VLM providers:', providers)
"
```

**预期结果**:
```
Registered VLM providers: ['dashscope']
```

---

### 变更 1.5: 添加 MySQL 连接配置

**文件**: `shared/rag_shared/config/experiment.py`

**变更类型**: 修改

**具体变更**:
```python
# 在 ExperimentConfig 类中，找到存储配置部分，添加 MySQL 字段
    # ── 存储 ──
    qdrant_url: str = "http://localhost:6333"
    qdrant_path: str = "data/vectordb"
    mysql_url: str = "mysql+pymysql://rag_user:rag_password@localhost:3306/rag_db"
    mysql_host: str = "localhost"          # 新增
    mysql_port: int = 3306                 # 新增
    mysql_user: str = "rag_user"           # 新增
    mysql_password: str = "rag_password"   # 新增
    mysql_database: str = "rag_db"         # 新增
    collection_name_override: Optional[str] = None
```

**验证方法**:
```bash
cd shared
poetry run python -c "
from rag_shared.config.experiment import ExperimentConfig
config = ExperimentConfig()
print('MySQL host:', config.mysql_host)
print('MySQL port:', config.mysql_port)
print('MySQL database:', config.mysql_database)
"
```

**预期结果**:
```
MySQL host: localhost
MySQL port: 3306
MySQL database: rag_db
```

---

### 变更 1.6: 创建 VLM Provider 测试脚本

**文件**: `services/ingestion/tests/test_vlm_provider.py`

**变更类型**: 新增

**用途**: 测试 VLM Provider 的图像摘要生成和多模态生成功能

**验证方法**:
```bash
cd services/ingestion
# 需要设置 DASHSCOPE_API_KEY 环境变量
export DASHSCOPE_API_KEY="your_key"
poetry run python tests/test_vlm_provider.py
```

**预期结果**:
- 如果没有 API Key，输出错误提示
- 如果有 API Key 且测试图片存在，输出图像摘要和多模态生成结果

---

## Phase 2: 解析与摘要生成（Ingestion 侧）

### 变更 2.1: 增强 PDF 解析器（图片分类 + 周围文本提取）

**文件**: `services/ingestion/app/parsing/multimodal_parser.py`

**变更类型**: 修改（扩展）

**具体变更**:
```python
# 1. 在导入部分添加 ImageType
from rag_shared.core.types import ImageType

# 2. 在 _is_toc_page 方法之后添加两个新方法

    def _classify_image_type(
        self,
        image_info: Dict[str, Any],
        page_text: str
    ) -> ImageType:
        """基于启发式规则分类图片类型。"""
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
        """提取图片周围的文本作为上下文。"""
        if not page_text or not image_bbox:
            return ""

        lines = page_text.split("\n")
        lines = [line.strip() for line in lines if line.strip()]

        # 取前后各 context_lines 行
        if len(lines) <= context_lines * 2:
            surrounding = "\n".join(lines)
        else:
            before = lines[:context_lines]
            after = lines[-context_lines:]
            surrounding = "\n".join(before + after)

        # 清理：去除过长的行（可能是噪音）
        cleaned_lines = []
        for line in surrounding.split("\n"):
            if len(line) < 200:
                cleaned_lines.append(line)

        return "\n".join(cleaned_lines[:context_lines * 2])

# 3. 在 parse 方法中，修改图片提取部分
                for img_info in enumerate(image_list):
                    xref = img_info[1][0]  # img_info is (index, img_data)

                    # ... 提取图片数据和尺寸的代码保持不变 ...

                    # 构建图片信息字典
                    img_dict = {
                        "data": image_bytes,
                        "bbox": bbox,
                        "format": image_ext,
                        "width": width,
                        "height": height,
                    }

                    # 分类图片类型（新增）
                    image_type = self._classify_image_type(img_dict, text)
                    img_dict["image_type"] = image_type

                    # 提取周围文本（新增）
                    surrounding_text = self._extract_surrounding_text(text, bbox)
                    img_dict["surrounding_text"] = surrounding_text

                    images.append(img_dict)
```

**验证方法**:
```bash
cd services/ingestion
poetry run python -c "
from app.parsing.multimodal_parser import MultimodalPDFParser
from rag_shared.core.types import ImageType

parser = MultimodalPDFParser()

# 测试图片分类
test_image = {'width': 800, 'height': 400}
test_text = '这是一个流程图，展示了申请步骤'
image_type = parser._classify_image_type(test_image, test_text)
print('Classified as:', image_type.value)

# 测试周围文本提取
test_text = '第一行\n第二行\n第三行\n第四行\n第五行'
surrounding = parser._extract_surrounding_text(test_text, (0, 0, 100, 100))
print('Surrounding text lines:', len(surrounding.split('\n')))
"
```

**预期结果**:
```
Classified as: flowchart
Surrounding text lines: 6
```

---

