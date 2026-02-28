
### 变更 2.2: 修改多模态切分器（集成 VLM 摘要生成）

**文件**: `services/ingestion/app/components/chunkers/multimodal.py`

**变更类型**: 修改（重构）

**具体变更**:
1. 修改类文档字符串，说明使用 VLM 生成图像摘要
2. 修改 `create_splitter()` 方法，接收 `api_key`, `vlm_model`, `enable_vlm_summary` 参数
3. 添加 `MultimodalSplitter.__init__()` 方法，初始化 VLM Provider
4. 修改 `get_nodes_from_documents()` 方法：
   - 调用 `_generate_image_summary()` 为每张图片生成摘要
   - Parent Node 添加 `image_summaries` 字段
   - Child Node 的 `text` 字段存储完整摘要（而非简短描述）
   - Child Node 的 `node_type` 改为 `"image_summary"`
5. 添加 `_generate_image_summary()` 方法，调用 VLM Provider 生成摘要

**验证方法**:
```bash
cd services/ingestion
poetry run python -c "
from rag_shared.core.registry import ComponentRegistry
import app.components.chunkers.multimodal

chunker_class = ComponentRegistry.get_chunker('multimodal')
print('Chunker class:', chunker_class.__name__)

splitter = chunker_class().create_splitter(
    chunk_size=1024,
    chunk_overlap=0,
    enable_vlm_summary=False
)
print('Splitter created:', type(splitter).__name__)
print('VLM enabled:', splitter.enable_vlm_summary)
"
```

**预期结果**:
```
Chunker class: MultimodalChunker
Splitter created: MultimodalSplitter
VLM enabled: False
```

---

### 变更 2.3: 扩展 MySQL Schema

**文件**: `scripts/migrate_multimodal_schema.sql`

**变更类型**: 修改（扩展）

**具体变更**: 添加 `image_type` 和 `summary` 字段

**验证方法**:
```bash
mysql -u rag_user -p rag_db < scripts/migrate_multimodal_schema.sql
```

---

## Phase 3: 检索与生成（Inference 侧）

### 变更 3.1: 创建 MySQL 客户端

**文件**: `services/inference/app/storage/mysql_client.py`

**变更类型**: 新增

**关键方法**: `get_nodes_by_ids()`, `get_node_by_id()`

**验证方法**:
```bash
cd services/inference
poetry run python -c "
from app.storage.mysql_client import MySQLClient
print('MySQLClient imported successfully')
"
```

---

### 变更 3.2-3.6: Inference 服务修改

详见完整文档。

---

## 变更文件清单

### Phase 1: 基础设施（6 个文件）
1. `shared/rag_shared/core/types.py`
2. `shared/rag_shared/core/registry.py`
3. `services/ingestion/app/components/providers/vlm.py`
4. `services/ingestion/app/components/providers/__init__.py`
5. `shared/rag_shared/config/experiment.py`
6. `services/ingestion/tests/test_vlm_provider.py`

### Phase 2: 解析与摘要生成（3 个文件）
7. `services/ingestion/app/parsing/multimodal_parser.py`
8. `services/ingestion/app/components/chunkers/multimodal.py`
9. `scripts/migrate_multimodal_schema.sql`

### Phase 3: 检索与生成（6 个文件）
10. `services/inference/app/storage/mysql_client.py`
11. `services/inference/app/services/retrieval.py`
12. `services/inference/app/components/providers/vlm.py`
13. `services/inference/app/components/providers/__init__.py`
14. `services/inference/app/agent/nodes.py`
15. `services/inference/app/agent/workflow.py`

**总计**: 15 个文件变更（6 个新增，9 个修改）

---

## 快速验证脚本

```bash
#!/bin/bash
# 快速验证所有变更

echo "=== Phase 1: 基础设施 ==="
cd shared && poetry run python -c "from rag_shared.core.types import ImageType, BaseVLMProvider; print('✓ Types OK')"
cd ../services/ingestion && poetry run python -c "from rag_shared.core.registry import ComponentRegistry; import app.components.providers.vlm; print('✓ VLM Provider OK')"

echo "=== Phase 2: 解析与摘要 ==="
cd services/ingestion && poetry run python -c "from app.parsing.multimodal_parser import MultimodalPDFParser; print('✓ Parser OK')"
cd services/ingestion && poetry run python -c "from rag_shared.core.registry import ComponentRegistry; import app.components.chunkers.multimodal; print('✓ Chunker OK')"

echo "=== Phase 3: 检索与生成 ==="
cd services/inference && poetry run python -c "from app.storage.mysql_client import MySQLClient; print('✓ MySQL Client OK')"
cd services/inference && poetry run python -c "from app.services.retrieval import RetrievalService; print('✓ Retrieval Service OK')"
cd services/inference && poetry run python -c "from app.agent.nodes import agent_node; print('✓ Agent Node OK')"

echo "=== 所有验证完成 ==="
```

保存为 `scripts/verify_multimodal_changes.sh` 并执行：
```bash
chmod +x scripts/verify_multimodal_changes.sh
./scripts/verify_multimodal_changes.sh
```
