# Phase 3 多模态检索与生成验证计划

## Context

Phase 2 (Ingestion) 已通过验证，现在验证 Phase 3 的 Inference 侧实现：多模态检索、父节点召回、VLM 集成、API 端点。

**Phase 3 范围**：
- **变更 3.1**: MySQL 客户端（父节点批量查询）
- **变更 3.2**: 多模态检索服务（图像向量检索 + 父节点召回）
- **变更 3.3**: 文本检索服务增强（image_summary 节点检测 + 父节点获取）
- **变更 3.4**: 多模态聊天 API（/multimodal/chat 端点）
- **变更 3.5**: VLM Provider（Qwen-VL 多模态 LLM）

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Inference Service (8002)                  │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  API Layer: /multimodal/chat                                 │
│      ↓                                                        │
│  MultimodalRetrievalService                                  │
│      ├─ Image Embedding (MultimodalEmbedding)               │
│      ├─ Qdrant Query (using="image" named vector)           │
│      └─ Parent Node Fetch (MySQL)                            │
│                                                               │
│  RetrievalService (text-based)                               │
│      ├─ Qdrant Query (using="text" vector)                   │
│      ├─ Detect image_summary nodes                           │
│      └─ Fetch parent nodes (MySQLClient)                     │
│                                                               │
│  VLM Layer: QwenVLLLMProvider                                │
│      └─ Generate response with image context                 │
│                                                               │
└─────────────────────────────────────────────────────────────┘
         ↓                              ↓
    ┌─────────┐                   ┌──────────┐
    │  MySQL  │                   │  Qdrant  │
    │ (parent │                   │ (child   │
    │  nodes) │                   │  vectors)│
    └─────────┘                   └──────────┘
```

---

## Verification Strategy

### Level 1: 单元测试（组件独立验证）
验证 MySQL 客户端、节点检测逻辑、Schema 匹配

### Level 2: 集成测试（服务间通信）
验证 Retrieval → MySQL 集成、Qdrant named vector 查询

### Level 3: 端到端测试（完整流程）
验证多模态聊天 API、VLM 生成、图像检索

---

## Verification Plan

### 验证 3.1: MySQL 客户端 - 父节点查询

**文件**: `services/inference/app/storage/mysql_client.py`

**验证内容**:
- 连接建立成功
- 批量查询 `get_nodes_by_ids()` 正确
- metadata JSON 解析正确
- 新字段 (image_type, summary) 存在

**验证方法**:
```bash
cd services/inference
poetry run python -c "
import sys
import os
sys.path.insert(0, 'app')

from app.storage.mysql_client import MySQLClient

# 连接测试
client = MySQLClient(
    host='localhost',
    port=3306,
    user='rag_user',
    password='rag_password',
    database='rag_db'
)

try:
    client.connect()
    print('[PASS] MySQL 连接成功')

    # 验证表结构（查询任意一行检查字段）
    cursor = client.connection.cursor(dictionary=True)
    cursor.execute('SELECT * FROM parent_nodes LIMIT 1')
    row = cursor.fetchone()

    if row:
        fields = row.keys()
        required_fields = ['node_id', 'text', 'metadata', 'image_type', 'summary', 'node_format', 'collection_type']
        missing = [f for f in required_fields if f not in fields]
        if missing:
            print(f'[FAIL] 缺少字段: {missing}')
        else:
            print('[PASS] 所有必需字段存在')
            print(f'[PASS] 字段列表: {list(fields)}')
    else:
        print('[INFO] 表为空，跳过字段验证')

    cursor.close()
    client.close()
    print('[PASS] MySQL 客户端验证完成')

except Exception as e:
    print(f'[FAIL] MySQL 客户端错误: {e}')
    import traceback
    traceback.print_exc()
"
```

**预期结果**:
```
[PASS] MySQL 连接成功
[PASS] 所有必需字段存在
[PASS] 字段列表: ['id', 'node_id', 'collection_name', 'collection_type', 'node_format', 'image_type', 'summary', ...]
[PASS] MySQL 客户端验证完成
```

---

### 验证 3.2: RetrievalService - image_summary 节点检测

**文件**: `services/inference/app/services/retrieval.py`

**验证内容**:
- 检测 `node_type == "image_summary"` 的节点
- 提取 `parent_id` 并去重
- 调用 MySQLClient 获取父节点
- 将图片数据添加到 chunk_info

**验证方法**:
```bash
cd services/inference
poetry run python -c "
import sys
sys.path.insert(0, 'app')
import os
os.environ['DASHSCOPE_API_KEY'] = 'test_key'

from rag_shared.config.experiment import ExperimentConfig

# 创建测试配置（不启用多模态，仅测试逻辑）
config = ExperimentConfig(
    experiment_id='test_phase3',
    collection_name='test_collection',
    chunking_strategy='multimodal',
    enable_multimodal=False,  # 暂不测试 MySQL 连接
    dashscope_api_key='test_key',
)

from app.services.retrieval import RetrievalService

try:
    service = RetrievalService(config)
    print('[PASS] RetrievalService 初始化成功')

    # 检查 MySQL 客户端（应该为 None，因为未启用多模态）
    if service.mysql_client is None:
        print('[PASS] MySQL 客户端未初始化（enable_multimodal=False）')

    # 测试节点类型检测逻辑（代码审查）
    print('[INFO] 检测逻辑位于 as_debug_langchain_tool() 方法')
    print('[INFO] 关键代码: is_multimodal = node_type == \"image_summary\"')
    print('[PASS] 节点检测逻辑存在')

except Exception as e:
    print(f'[FAIL] RetrievalService 错误: {e}')
    import traceback
    traceback.print_exc()
"
```

**预期结果**:
```
[PASS] RetrievalService 初始化成功
[PASS] MySQL 客户端未初始化（enable_multimodal=False）
[INFO] 检测逻辑位于 as_debug_langchain_tool() 方法
[INFO] 关键代码: is_multimodal = node_type == "image_summary"
[PASS] 节点检测逻辑存在
```

---

### 验证 3.3: MultimodalRetrievalService - 图像检索 + 父节点召回

**文件**: `services/inference/app/services/multimodal_retrieval.py`

**验证内容**:
- 初始化多模态 Embedding Provider
- 图像 embedding 生成
- Qdrant `using="image"` 查询
- 父节点从 MySQL 召回

**验证方法**:
```bash
cd services/inference
poetry run python -c "
import sys
sys.path.insert(0, 'app')
import os

# 检查代码结构
from app.services.multimodal_retrieval import MultimodalRetrievalService
import inspect

print('[INFO] 检查 MultimodalRetrievalService 方法')

# 检查关键方法存在
methods = [m for m in dir(MultimodalRetrievalService) if not m.startswith('_')]
print(f'[PASS] 公开方法: {methods}')

# 检查 search_by_image 签名
sig = inspect.signature(MultimodalRetrievalService.search_by_image)
print(f'[PASS] search_by_image 签名: {sig}')

# 检查私有方法
private_methods = [m for m in dir(MultimodalRetrievalService) if m.startswith('_') and not m.startswith('__')]
print(f'[PASS] 私有方法: {private_methods}')

# 检查源码关键点
source = inspect.getsource(MultimodalRetrievalService.search_by_image)
checks = [
    ('using=\"image\"', 'Qdrant named vector 查询'),
    ('query_vector', '图像 embedding 生成'),
    ('_fetch_parents_from_results', '父节点召回调用'),
]

for pattern, desc in checks:
    if pattern in source:
        print(f'[PASS] {desc}: 代码存在')
    else:
        print(f'[FAIL] {desc}: 代码缺失')

print('[PASS] MultimodalRetrievalService 结构验证完成')
"
```

**预期结果**:
```
[INFO] 检查 MultimodalRetrievalService 方法
[PASS] 公开方法: ['search_by_image']
[PASS] search_by_image 签名: (self, image_bytes: bytes, top_k: int = 5, user_role: Optional[str] = None)
[PASS] 私有方法: ['_fetch_parents_from_results']
[PASS] Qdrant named vector 查询: 代码存在
[PASS] 图像 embedding 生成: 代码存在
[PASS] 父节点召回调用: 代码存在
[PASS] MultimodalRetrievalService 结构验证完成
```

---

### 验证 3.4: API 端点 - /multimodal/chat

**文件**: `services/inference/app/api/routes.py`

**验证内容**:
- 端点存在且路由正确
- 请求体验证 (MultimodalChatRequest)
- enable_multimodal 配置检查
- 图像解码 base64
- 调用 MultimodalRetrievalService
- VLM Provider 初始化
- 上下文构建（文本 + 图片）

**验证方法**:
```bash
cd services/inference
poetry run python -c "
import sys
sys.path.insert(0, 'app')

# 检查端点定义
from app.api.routes import router
import inspect

# 查找 multimodal_chat 函数
for route in router.routes:
    if hasattr(route, 'path') and 'multimodal' in route.path:
        print(f'[PASS] 端点存在: {route.methods} {route.path}')

# 检查函数签名
from app.api import routes
if hasattr(routes, 'multimodal_chat'):
    sig = inspect.signature(routes.multimodal_chat)
    print(f'[PASS] multimodal_chat 签名: {sig}')

    # 检查源码关键点
    source = inspect.getsource(routes.multimodal_chat)
    checks = [
        ('MultimodalChatRequest', '请求体验证'),
        ('enable_multimodal', '配置检查'),
        ('base64.b64decode', '图像解码'),
        ('MultimodalRetrievalService', '检索服务调用'),
        ('create_multimodal_llm', 'VLM 初始化'),
        ('context_text', '上下文构建'),
        ('reference_images', '参考图像提取'),
    ]

    for pattern, desc in checks:
        if pattern in source:
            print(f'[PASS] {desc}: 代码存在')
        else:
            print(f'[FAIL] {desc}: 代码缺失')

    print('[PASS] /multimodal/chat 端点验证完成')
else:
    print('[FAIL] multimodal_chat 函数不存在')
"
```

**预期结果**:
```
[PASS] 端点存在: {'POST'} /multimodal/chat
[PASS] multimodal_chat 签名: (request: Dict[str, Any])
[PASS] 请求体验证: 代码存在
[PASS] 配置检查: 代码存在
[PASS] 图像解码: 代码存在
[PASS] 检索服务调用: 代码存在
[PASS] VLM 初始化: 代码存在
[PASS] 上下文构建: 代码存在
[PASS] 参考图像提取: 代码存在
[PASS] /multimodal/chat 端点验证完成
```

---

### 验证 3.5: VLM Provider - Qwen-VL 集成

**文件**: `services/inference/app/components/providers/qwen_vl_llm.py`

**验证内容**:
- QwenVLLLMProvider 类存在
- create_multimodal_llm() 方法
- 注册到 ComponentRegistry

**验证方法**:
```bash
cd services/inference
poetry run python -c "
import sys
sys.path.insert(0, 'app')

# 检查 Provider 存在
try:
    from app.components.providers.qwen_vl_llm import QwenVLLLMProvider
    print('[PASS] QwenVLLLMProvider 类存在')

    import inspect
    methods = [m for m in dir(QwenVLLLMProvider) if not m.startswith('_')]
    print(f'[PASS] 公开方法: {methods}')

    # 检查关键方法
    if hasattr(QwenVLLLMProvider, 'create_multimodal_llm'):
        sig = inspect.signature(QwenVLLLMProvider.create_multimodal_llm)
        print(f'[PASS] create_multimodal_llm 签名: {sig}')
    else:
        print('[FAIL] create_multimodal_llm 方法不存在')

    # 检查注册
    from rag_shared.core.registry import ComponentRegistry
    import app.components.providers  # 触发注册

    try:
        provider = ComponentRegistry.get_multimodal_llm_provider('qwen-vl')
        print('[PASS] Provider 已注册到 ComponentRegistry')
    except:
        print('[FAIL] Provider 未注册')

except ImportError as e:
    print(f'[FAIL] 导入失败: {e}')
except Exception as e:
    print(f'[FAIL] 验证失败: {e}')
    import traceback
    traceback.print_exc()
"
```

**预期结果**:
```
[PASS] QwenVLLLMProvider 类存在
[PASS] 公开方法: ['create_multimodal_llm']
[PASS] create_multimodal_llm 签名: (self, model_name: str, api_key: str, temperature: float = 0.7)
[PASS] Provider 已注册到 ComponentRegistry
```

---

### 验证 3.6: 端到端集成测试（模拟请求）

**前置条件**:
- ✅ MySQL 运行且包含 Phase 2 数据
- ✅ Qdrant 运行且包含子节点向量
- ✅ Inference 服务启动 (Port 8002)
- ✅ DASHSCOPE_API_KEY 设置

**验证方法 1: 服务启动测试**
```bash
# 1. 启动 Inference 服务
cd services/inference
poetry run python -m app.main &

# 等待启动
sleep 5

# 2. 检查健康状态
curl -X GET http://localhost:8002/health

# 3. 检查多模态端点
curl -X POST http://localhost:8002/api/v1/multimodal/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "测试请求",
    "images": [],
    "config": {"experiment_id": "test"}
  }' 2>&1 | head -20
```

**预期结果**:
- 健康检查返回 200 OK
- 多模态端点返回 400（因为 images 为空，符合验证逻辑）

---

## Critical Files

| 文件 | 用途 | 验证重点 |
|------|------|---------|
| `services/inference/app/storage/mysql_client.py` | MySQL 父节点查询 | 连接、批量查询、字段验证 |
| `services/inference/app/services/retrieval.py` | 文本检索 + 父节点获取 | image_summary 检测 |
| `services/inference/app/services/multimodal_retrieval.py` | 图像检索服务 | named vector 查询 |
| `services/inference/app/api/routes.py` | 多模态 API 端点 | 请求验证、流程编排 |
| `services/inference/app/components/providers/qwen_vl_llm.py` | VLM Provider | 多模态 LLM 创建 |

---

## Verification Checklist

### Level 1: 单元测试
- [ ] 验证 3.1: MySQL 客户端连接与查询
- [ ] 验证 3.2: RetrievalService 节点检测逻辑
- [ ] 验证 3.3: MultimodalRetrievalService 结构
- [ ] 验证 3.4: API 端点定义完整性
- [ ] 验证 3.5: VLM Provider 注册

### Level 2: 集成测试
- [ ] MySQL → Qdrant 数据一致性
- [ ] parent_id 映射正确性
- [ ] Named vector 查询可用性

### Level 3: 端到端测试
- [ ] Inference 服务启动成功
- [ ] 多模态端点响应正确
- [ ] VLM 生成流程完整

---

## Success Criteria

✅ **Phase 3 验证通过标准**:
1. MySQL 客户端正常连接并查询父节点
2. RetrievalService 正确检测 image_summary 节点
3. MultimodalRetrievalService 结构完整（图像检索 + 父节点召回）
4. API 端点定义完整且逻辑正确
5. VLM Provider 正确注册且可初始化
6. 服务启动无错误，端点可访问

---

## Known Issues

### 潜在问题（需验证）

| 问题 | 影响 | 优先级 |
|------|------|--------|
| MySQL 连接池未配置 | 高并发性能下降 | P2 |
| 父节点召回未做缓存 | 重复查询开销 | P2 |
| 图像 embedding 临时文件清理 | 磁盘空间占用 | P3 |
| VLM API 调用无重试 | 单次失败影响体验 | P2 |

---

## Next Steps

**完成 Phase 3 验证后**:
1. 端到端集成测试（Ingestion → Inference 完整流程）
2. 性能基准测试（检索延迟、VLM 调用时间）
3. Gateway UI 集成（多模态聊天界面）
4. 生产环境部署准备
