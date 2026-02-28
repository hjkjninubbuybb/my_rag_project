# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 1. 项目概览

Enterprise-grade **Multimodal Agentic RAG** (Retrieval-Augmented Generation) system with full-dimension ablation experiment support.

**核心特性**：
- **微服务架构**: 3 services (Ingestion, Inference, Gateway) + shared library + CLI tool
- **多模态处理**: PDF image-text pair extraction, VLM summarization, hierarchical storage (MySQL + Qdrant)
- **Agent 推理**: LangGraph ReAct workflow, parallel question routing, SSE streaming
- **消融实验**: Grid-based ablation testing across chunking, retrieval, and reranking dimensions
- **角色过滤**: Chinese filename-based role extraction (teacher/student/reviewer/admin)
- **轻量稀疏向量**: jieba-based sparse vectors (~15MB) replacing BGE-M3 (~2GB)

**技术栈**: LlamaIndex, LangGraph, Qdrant, MySQL, FastAPI, Gradio, DashScope (Qwen-Plus, Qwen-VL)

---

## 2. 快速开始

### 环境要求
- Python 3.10+
- Poetry (依赖管理)
- Docker & Docker Compose
- `.env` file with `DASHSCOPE_API_KEY`

### 一键启动（推荐）

```bash
# Docker Compose 启动全部服务
docker compose up -d

# 访问服务
# - Gateway UI: http://localhost:7860
# - Ingestion API: http://localhost:8001/docs
# - Inference API: http://localhost:8002/docs
# - Qdrant UI: http://localhost:6333/dashboard
```

### 本地开发（各服务独立 Poetry 环境）

```bash
# 1. 安装 shared 库（所有服务的公共依赖）
cd shared && poetry install

# 2. 启动基础设施
docker run -d -p 6333:6333 qdrant/qdrant
docker run -d -p 3306:3306 -e MYSQL_ROOT_PASSWORD=root mysql:8.0

# 3. 初始化 MySQL（执行 scripts/init_mysql.sql）
mysql -h localhost -u root -p < scripts/init_mysql.sql

# 4. 启动 Ingestion 服务（Port 8001）
cd services/ingestion && poetry install && poetry run python -m app.main

# 5. 启动 Inference 服务（Port 8002）
cd services/inference && poetry install && poetry run python -m app.main

# 6. 启动 Gateway UI（Port 7860）
cd services/gateway && poetry install && poetry run python -m app.main
```

### CLI 评测工具

```bash
cd cli && poetry install

# 单配置评测
poetry run rag-eval --config ../configs/default.yaml --limit 10

# 消融网格评测
poetry run rag-eval --grid ../configs/ablation_grid.yaml --limit 10

# 批量入库
poetry run rag-eval --ingest --input-dir ../data/uploads/documents
```

---

## 3. 架构设计

### 3.1 微服务概览

| Service | Port | Responsibility | Key Dependencies | Storage |
|---------|------|---------------|-----------------|---------|
| **Ingestion** | 8001 | File parsing, chunking, embedding, Qdrant storage, multimodal PDF extraction | numpy>=2.0, llama-index, fastapi, pymupdf, pillow | Qdrant (child nodes), MySQL (parent nodes), SQLite (metadata) |
| **Inference** | 8002 | Query processing, LangGraph agent workflow, SSE streaming, multimodal retrieval | numpy<2.0, langgraph, langchain, sse-starlette | Qdrant (read), MySQL (read) |
| **Gateway** | 7860 | Gradio UI, httpx proxy to backend services | gradio, httpx, httpx-sse | None (stateless) |
| **Qdrant** | 6333 | Vector database (text + image named vectors) | Docker container | Named vectors: `text` (1536-dim), `image` (2560-dim) |
| **MySQL** | 3306 | Parent node storage (full images + metadata) | Docker container | `parent_nodes` table (id, collection_name, file_name, text, metadata) |
| **CLI** | — | Batch evaluation & ingestion | httpx, pandas, tqdm | Local reports (`data/reports/`) |

### 3.2 核心设计模式

#### ComponentRegistry + Decorators

**位置**: `shared/rag_shared/core/registry.py`

**机制**: 使用装饰器注册组件，按名称查找实例化。每个服务通过 `__init__.py` 导入注册自己的实现。

**8 种组件类型**:
1. `chunker` - 文档切片器
2. `llm_provider` - LLM 提供商
3. `embedding_provider` - Embedding 提供商
4. `reranker_provider` - Reranker 提供商
5. `multimodal_embedding_provider` - 多模态 Embedding 提供商
6. `multimodal_llm_provider` - 多模态 LLM 提供商
7. `image_processor` - 图像处理器
8. `vlm_provider` - VLM (Vision-Language Model) 提供商

**使用示例**:
```python
# 注册组件
@ComponentRegistry.chunker("fixed")
class FixedChunker(BaseChunker):
    ...

# 查找组件
chunker_class = ComponentRegistry.get_chunker("fixed")
chunker = chunker_class()
```

#### Abstract Base Classes (ABCs)

**位置**: `shared/rag_shared/core/types.py`

**8 个基类**:
- `BaseChunker` - 文档切片器基类
- `BaseLLMProvider` - LLM 提供商基类
- `BaseEmbeddingProvider` - Embedding 提供商基类
- `BaseRerankerProvider` - Reranker 提供商基类
- `BaseMultimodalEmbeddingProvider` - 多模态 Embedding 提供商基类
- `BaseMultimodalLLMProvider` - 多模态 LLM 提供商基类
- `BaseImageProcessor` - 图像处理器基类
- `BaseVLMProvider` - VLM 提供商基类

**枚举类型**:
- `ImageType` - 图片类型枚举 (SCREENSHOT, FLOWCHART, TABLE, DIAGRAM, OTHER)

#### ExperimentConfig

**位置**: `shared/rag_shared/config/experiment.py`

**设计**: Frozen dataclass，不可变配置对象。

**关键属性**:
- `qdrant_endpoint` (property): 双模式 Qdrant 访问 - 优先使用 `qdrant_url`（HTTP），fallback 到 `qdrant_path`（本地路径）
- `ingestion_fingerprint` (property): 入库指纹，确保相同切片+Embedding 参数共享同一 collection

**多模态字段**:
- `enable_multimodal: bool` - 是否启用多模态
- `multimodal_embedding_provider: str` - 多模态 Embedding 提供商（默认 "qwen-vl"）
- `multimodal_embedding_model: str` - 多模态 Embedding 模型（默认 "qwen3-vl-embedding"）
- `multimodal_llm_model: str` - 多模态 LLM 模型（默认 "qwen-vl-max"）
- `image_embedding_dim: int` - 图像向量维度（默认 2560）
- `image_max_size: int` - 图像最大边长 px（默认 1024）
- `image_compression_quality: int` - JPEG 压缩质量（默认 85）
- `image_vector_weight: float` - 图像向量权重（默认 0.7）
- `text_vector_weight: float` - 文本向量权重（默认 0.3）
- `user_role: Optional[str]` - 用户角色过滤（"teacher" | "student" | "reviewer" | "defense_committee" | None=管理员）

**fingerprint 计算**:
- `enable_multimodal=True` 时，fingerprint 包含多模态参数（`multimodal_embedding_provider`, `multimodal_embedding_model`, `image_embedding_dim`）
- **不包含**稀疏模型信息（改变稀疏模型需手动删除 collection）

#### 层级节点存储

**设计**: Parent-Child 分离存储，实现完整图片与摘要的分层管理。

**流程**:
1. `MultimodalChunker` 返回 `(parent_nodes, child_nodes)` tuple（区别于其他 Chunker 返回 `List[Node]`）
2. Parent nodes（含完整 base64 图片 + 上下文文本） → MySQL `parent_nodes` 表
3. Child nodes（VLM 生成的图片摘要文本） → Qdrant 向量索引
4. 检索时：Qdrant 召回 child nodes → 根据 `parent_id` 从 MySQL 查询完整 parent node

**检测机制**: Ingestion service 通过 `isinstance(result, tuple)` 检测 Chunker 返回值类型，自动路由存储逻辑。

#### Named Vectors in Qdrant

**设计**: 多模态 collection 使用 Named Vectors 存储不同模态的向量。

**向量配置**:
- `text`: 1536-dim dense text embeddings (DashScope text-embedding-v4)
- `image`: 2560-dim dense image embeddings (Qwen3-VL-Embedding)
- 稀疏向量（sparse）: jieba-based BM25-style sparse vectors

**权重设置**: 通过 `image_vector_weight` 和 `text_vector_weight` 控制多模态检索的融合权重。

#### 角色过滤（Role-Based Access Control）

**位置**: `shared/rag_shared/utils/role_mapper.py`

**机制**: 从中文文件名自动提取角色关键词，映射到角色标识，存储在 node metadata 中。

**角色映射表**:

| 中文关键词 | 角色标识 | 说明 |
|-----------|---------|------|
| 指导老师 | `teacher` | 查看指导老师操作手册 |
| 学生 | `student` | 查看学生操作手册 |
| 评阅专家 | `reviewer` | 查看评阅流程 |
| 答辩组 | `defense_committee` | 查看答辩流程 |
| （无匹配） | `common` | 通用文档，所有角色可见 |
| （None） | （管理员） | 查看所有文档，无过滤 |

**检索过滤**:
- `user_role=None`: 管理员，查看所有文档
- `user_role="teacher"`: 仅查看 `user_role="teacher"` 或 `user_role="common"` 的文档

#### 独立 Poetry 环境

**设计**: 每个服务独立 `pyproject.toml` + `poetry.lock` + `.venv/`，解决依赖冲突。

**关键依赖冲突**:
- Ingestion: `numpy>=2.0` (MinerU 依赖)
- Inference: `numpy<2.0` (LangChain 依赖)

**shared 库安装**:
```toml
# services/*/pyproject.toml
[tool.poetry.dependencies]
rag-shared = {path = "../../shared", develop = true}
```

#### SSE 流式传输

**Inference Service**:
- LangGraph `astream_events()` → SSE (Server-Sent Events)
- Event types: `token`, `rewrite`, `chunks`, `done`, `error`

**Gateway Service**:
- `httpx-sse` 代理 Inference SSE → Gradio 前端
- 实时渲染 token + 检索 chunks

### 3.3 数据流与存储

#### 数据流 1: Ingestion Flow（文档入库）

```
┌─────────────┐
│  PDF File   │
└─────┬───────┘
      │
      ▼
┌─────────────────────────┐
│  PyMuPDF Parser         │ ← Extract images + context text
└─────┬───────────────────┘
      │
      ▼
┌─────────────────────────┐
│  PolicyCleaner          │ ← Remove headers/footers/TOC
└─────┬───────────────────┘
      │
      ▼
┌─────────────────────────┐
│  MultimodalChunker      │ ← Image-text pair + VLM summarization
└─────┬───────────────────┘
      │
      ▼
  (Parent, Child) Tuple
      │
      ├──────────────────────┐
      │                      │
      ▼                      ▼
┌─────────────┐      ┌─────────────┐
│   MySQL     │      │   Qdrant    │
│ parent_nodes│      │ child nodes │
│ (full image)│      │ (summaries) │
└─────────────┘      └─────────────┘
```

#### 数据流 2: Retrieval Flow（混合检索）

```
┌─────────────┐
│ User Query  │
└─────┬───────┘
      │
      ├────────────────────┬────────────────────┐
      │                    │                    │
      ▼                    ▼                    ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│Text Embedding│  │Sparse Vector│  │Image Embed  │
│(DashScope)   │  │(jieba BM25) │  │(Qwen-VL)    │
└─────┬────────┘  └─────┬────────┘  └─────┬───────┘
      │                 │                  │
      └─────────────────┼──────────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │  Qdrant Hybrid  │
              │  Search         │
              └─────┬───────────┘
                    │
                    ▼
              ┌─────────────────┐
              │  Reranker       │
              │  (DashScope)    │
              └─────┬───────────┘
                    │
                    ▼
              ┌─────────────────┐
              │  MySQL Lookup   │ ← Fetch parent nodes by child_id
              │  (parent_nodes) │
              └─────┬───────────┘
                    │
                    ▼
              ┌─────────────────┐
              │  VLM Context    │ ← Qwen-VL-Max multimodal reasoning
              │  (Qwen-VL)      │
              └─────────────────┘
```

#### 数据流 3: Agent Flow（LangGraph 推理）

```
┌─────────────┐
│ User Query  │
└─────┬───────┘
      │
      ▼
┌─────────────────────────┐
│  summarize              │ ← Compress last 6 messages (skip if <4)
└─────┬───────────────────┘
      │
      ▼
┌─────────────────────────┐
│  analyze_rewrite        │ ← LLM question decomposition (JSON output)
└─────┬───────────────────┘
      │
      ▼
┌─────────────────────────┐
│  route                  │ ← Send() parallel dispatch
└─────┬───────────────────┘
      │
      ├──────────┬──────────┬──────────┐
      │          │          │          │
      ▼          ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ ReAct    │ │ ReAct    │ │ ReAct    │ │ ReAct    │
│ Agent 1  │ │ Agent 2  │ │ Agent 3  │ │ Agent N  │
└─────┬────┘ └─────┬────┘ └─────┬────┘ └─────┬────┘
      │            │            │            │
      └────────────┴────────────┴────────────┘
                   │
                   ▼
         ┌─────────────────────────┐
         │  aggregate              │ ← Single answer: passthrough
         │                         │    Multi answers: LLM merge
         └─────┬───────────────────┘
               │
               ▼
         ┌─────────────────────────┐
         │  SSE Stream Response    │
         └─────────────────────────┘
```

**ReAct Subgraph (process_question)**:
```
agent → should_continue?
  ├─ [tools → agent] (loop, max 10 iterations)
  └─ extract_answer → END
```

---

## 4. 服务详解

### 4.1 Ingestion Service (Port 8001)

**职责**: 文档解析、切片、向量化、存储

#### API 端点

| 端点 | 方法 | 功能 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/v1/documents/upload` | POST | 上传文件并入库 | `multipart/form-data` (files + config JSON) | `IngestResponse` (hierarchical stats) |
| `/api/v1/documents/upload-multimodal` | POST | 上传 PDF 图文提取并入库 | `multipart/form-data` (file + config JSON) | `IngestResponse` (parent+child counts) |
| `/api/v1/documents/ingest` | POST | 路径列表入库 | `IngestRequest` (file_paths + config) | `IngestResponse` |
| `/api/v1/batch/ingest` | POST | 批量智能入库（按 fingerprint 去重） | `BatchIngestRequest` (configs + input_dir) | `BatchIngestResponse` (per-config results) |
| `/api/v1/collections` | GET | 列出所有 Qdrant collections | — | `List[CollectionInfo]` (name + point_count) |
| `/api/v1/collections/{name}/files` | GET | 列出 collection 中已入库文件 | — | `List[FileInfo]` (filenames) |
| `/api/v1/documents/{collection}/{filename}` | DELETE | 删除指定文档 | — | `DocumentDeleteResponse` |

#### 请求示例

**上传多模态 PDF**:
```bash
curl -X POST http://localhost:8001/api/v1/documents/upload-multimodal \
  -F "file=@manual.pdf" \
  -F 'config={"enable_multimodal": true, "collection_name": "manual_test", "user_role": "teacher"}'
```

**响应**:
```json
{
  "status": "success",
  "message": "Multimodal ingestion: 89 image nodes vectorized",
  "collection_name": "manual_qwen_plus_1024_256_50",
  "parent_count": 25,
  "child_count": 89,
  "vectorized_count": 89,
  "is_hierarchical": true
}
```

#### 关键实现

**IngestionService** (`services/ingestion/app/services/ingestion.py`):
- 检测 Chunker 返回值类型：`isinstance(result, tuple)` → 层级存储路由
- Parent nodes → MySQL (`MySQLClient.insert_parent_nodes()`)
- Child nodes → Qdrant (`VectorStoreManager.add_nodes()`)

**VectorStoreManager** (`services/ingestion/app/storage/vectordb.py`):
- 双模式 Qdrant：优先 `qdrant_url`（HTTP），fallback `qdrant_path`（本地）
- Named Vectors 配置：`text` (1536-dim), `image` (2560-dim)
- 稀疏向量支持：jieba-based BM25 sparse vectors

**DatabaseManager** (`services/ingestion/app/storage/metadata.py`):
- SQLite 元数据管理：`collections` + `documents` 表
- 快速查询文件列表、collection 信息

### 4.2 Inference Service (Port 8002)

**职责**: 查询处理、Agent 推理、SSE 流式输出

#### API 端点

| 端点 | 方法 | 功能 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/v1/chat/stream` | POST | SSE 流式对话 | `ChatRequest` (message + config + thread_id) | SSE events (token, rewrite, chunks, done, error) |
| `/api/v1/chat/reset` | POST | 重置对话状态 | `ChatResetRequest` (thread_id) | Status (MemorySaver 不支持 delete，客户端用新 thread_id) |
| `/api/v1/retrieval/search` | POST | 直接检索（不经过 Agent） | `RetrievalSearchRequest` (query + config + top_k) | `RetrievalSearchResponse` (nodes with text+score+source) |
| `/api/v1/evaluate/single` | POST | 单配置评测 | `EvaluateRequest` (config + dataset + limit) | `EvaluateResponse` (summary + details) |
| `/api/v1/multimodal/chat` | POST | 多模态对话（截图 + 文本 → 操作指导） | `MultimodalChatRequest` (message + images + config) | JSON (answer + reference_images + debug_info) |

#### SSE 事件类型

| Event | 说明 | Data 格式 |
|-------|------|----------|
| `token` | LLM 流式 token | `{"content": str}` |
| `rewrite` | 问题改写结果 | `{"questions": List[str]}` |
| `chunks` | 检索到的文档片段（Tool Artifact） | `[{"text": str, "score": float, "source_file": str}]` |
| `done` | 对话结束 | `{"status": "ok"}` |
| `error` | 错误信息 | `{"error": str}` |

#### 请求示例

**SSE 流式对话**:
```bash
curl -X POST http://localhost:8002/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "如何提交毕业论文？",
    "config": {"collection_name": "manual_test", "user_role": "student"},
    "thread_id": "abc123"
  }'
```

**多模态对话**:
```bash
curl -X POST http://localhost:8002/api/v1/multimodal/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "我点了提交按钮但没反应，怎么办？",
    "images": ["<base64_encoded_screenshot>"],
    "config": {"enable_multimodal": true, "collection_name": "manual_test", "user_role": "student"}
  }'
```

**响应**:
```json
{
  "answer": "根据您的截图，您当前在论文提交页面，但表单中必填字段 '论文标题' 未填写...",
  "reference_images": [
    {
      "page": 12,
      "file": "4-4 学生操作手册.pdf",
      "base64": "<reference_screenshot_base64>"
    }
  ],
  "debug_info": {
    "retrieval_count": 3,
    "context_images_count": 2,
    "user_role": "student",
    "collection_name": "manual_test"
  }
}
```

#### 关键实现

**create_graph()** (`services/inference/app/agent/workflow.py`):
- 构建 LangGraph StateGraph
- Nodes: `summarize`, `analyze_rewrite`, `route`, `process_question`, `aggregate`
- Checkpointer: `MemorySaver`（内存存储，重置用新 thread_id）
- Graph 缓存：按 `{llm_provider}_{llm_model}_{collection_name}` 缓存实例

**RetrievalService** (`services/inference/app/services/retrieval.py`):
- 混合检索：Dense (text embedding) + Sparse (jieba BM25)
- Reranker: DashScope `gte-rerank`
- 返回 `List[NodeWithScore]`

**MultimodalRetrievalService** (`services/inference/app/services/multimodal_retrieval.py`):
- 图文混合搜索：Image vector (Qwen-VL) + Text vector (DashScope)
- MySQL parent node lookup：根据 child node 的 `parent_id` 查询完整图片
- 返回 `List[dict]` (text + metadata with images)

### 4.3 Gateway Service (Port 7860)

**职责**: Gradio UI + HTTP 代理

#### 实现

**UI 组件** (`services/gateway/app/ui/app.py`):
- Tab 1: 文档上传（调用 Ingestion `/documents/upload`）
- Tab 2: 对话（调用 Inference `/chat/stream`，SSE 流式渲染）
- Tab 3: 检索测试（调用 Inference `/retrieval/search`）

**HTTP 客户端**:
- `IngestionClient` (`app/clients/ingestion.py`): `httpx` 同步客户端
- `InferenceClient` (`app/clients/inference.py`): `httpx-sse` SSE 流式客户端

**特点**:
- 纯 UI 网关，无业务逻辑
- Stateless（无状态）
- SSE 代理：`httpx-sse` → Gradio `gr.update()`

---

## 5. 核心实现

### 5.1 文档预处理（PolicyCleaner）

**位置**: `services/ingestion/app/parsing/cleaner.py`

**职责**: 政策规范类文档清洗，优化 Recursive Text Splitter 效果

**处理步骤**:
1. **去除页码和页眉页脚**
   - 页码：`第 X 页`, `Page X of Y`, 纯数字（≤4 位）
   - 页眉页脚：短文本（<10 字符）且包含"第"+"页"

2. **去除目录（TOC）** ⭐ 多格式检测
   - 目录标题：`#### 目 录`, `## 目录`, `# 目录`, `TOC`, `Table of Contents`
   - 目录项格式：
     - `数字 标题 .........页码`（如 `1 绪论 .........1`）
     - `数字. 标题`（如 `1. 引言`）
     - `缩进+数字.`（如 `  12.`）
     - `数字.数字 标题`（如 `2.1 第七学期工作`）

3. **规范化空白**
   - 压缩连续空行（3+ → 2）

4. **合并段落** ⭐ Chunking 优化
   - 标题行：单独成行 + 后添加空行（提供清晰的 `\n\n` 分隔符）
   - 列表项：连续列表项之间不加空行
   - 段落：以句子结束符（`。！？；:.!?;`）结尾 → 输出 + 空行
   - 未结束段落：继续合并到 buffer

**自动路由**:
```python
from app.parsing.cleaner import get_cleaner_for_file

cleaner = get_cleaner_for_file(file_path, settings)
# - policy_data_dir → PolicyCleaner
# - manual_data_dir → ManualCleaner（无清洗）
# - 其他 → PolicyCleaner（默认）
```

### 5.2 切片策略

**完整对比表**:

| 策略 | 实现类 | 行为 | 文件位置 |
|------|--------|------|----------|
| `fixed` | `TokenTextSplitter` | 按 Token 数硬切（基准） | `services/ingestion/app/components/chunkers/fixed.py` |
| `recursive` | `RecursiveCharacterTextSplitter` | 按中文标点层级递归（`\n\n`, `\n`, `。`, `，`） | `services/ingestion/app/components/chunkers/recursive.py` |
| `sentence` | `SentenceSplitter` | 句子边界感知，父子节点生成 | `services/ingestion/app/components/chunkers/sentence.py` |
| `semantic` | `SemanticSplitterNodeParser` | Embedding 语义切分，breakpoint threshold 检测 | `services/ingestion/app/components/chunkers/semantic.py` |
| `multimodal` ⭐ | `MultimodalChunker` + `MultimodalSplitter` | 图文对提取 + VLM 摘要，返回 `(parent, child)` tuple | `services/ingestion/app/components/chunkers/multimodal.py` |

**Multimodal Chunker 流程**:
```
PDF → PyMuPDF 解析 → 提取图片 + 上下文文本
→ ImageProcessor (压缩/去重) → VLM 摘要（Qwen-VL-Max）
→ MultimodalSplitter (父子节点) → (parent_nodes, child_nodes)
```

### 5.3 稀疏向量实现（轻量替代 BGE-M3）

**位置**: `services/ingestion/app/components/providers/bgem3.py`

**设计目标**: 替代 BGE-M3 (~2GB 模型) → jieba (~15MB)

**实现细节**:

1. **Tokenization**:
   ```python
   jieba.cut(text) → List[str]
   ```

2. **Filtering**:
   - 60+ stopwords (`的`, `了`, `是`, `我`, `有`, `和`, `就`, `不`, `人`, `都`, `一个`, ...)
   - 最小长度 ≥ 2
   - 过滤纯数字

3. **Indexing**:
   ```python
   token → MD5 hash → 取前 8 位十六进制 → int(hex, 16)
   # 示例: "毕业论文" → "a3f5e1c2" → 2751529346
   ```

4. **Scoring** (BM25-style):
   ```python
   score = 1.0 + log(term_freq)
   # term_freq = 1 → score = 1.0
   # term_freq = 2 → score ≈ 1.69
   # term_freq = 3 → score ≈ 2.10
   ```

5. **性能对比**:

| 指标 | BGE-M3 | Jieba Sparse |
|------|--------|--------------|
| 模型大小 | ~2GB | ~15MB |
| 启动时间 | ~10s | <1s |
| 内存占用 | ~2.5GB | <50MB |
| 向量维度 | ~60K (动态) | ~4M (哈希空间) |
| 准确率 | 高（神经网络） | 中（规则+哈希） |

**使用场景**: 中文文档混合检索，轻量部署，快速启动。

### 5.4 LangGraph 工作流

**位置**: `services/inference/app/agent/workflow.py`

#### 主图结构

```python
graph = StateGraph(State)
graph.add_node("summarize", summarize)
graph.add_node("analyze_rewrite", analyze_rewrite)
graph.add_node("route", route)
graph.add_node("aggregate", aggregate)

graph.set_entry_point("summarize")
graph.add_edge("summarize", "analyze_rewrite")
graph.add_edge("analyze_rewrite", "route")
# route → Send() 动态分发到多个 process_question 子图
graph.add_edge("route", "aggregate")
graph.add_edge("aggregate", END)
```

#### 子图结构（process_question）⭐ 之前缺失

```python
# 每个子图独立的 ReAct loop
subgraph = StateGraph(AgentState)
subgraph.add_node("agent", agent_node)
subgraph.add_node("tools", tool_node)
subgraph.add_node("extract_answer", extract_answer)

subgraph.set_entry_point("agent")
subgraph.add_conditional_edges(
    "agent",
    should_continue,
    {
        "continue": "tools",
        "end": "extract_answer"
    }
)
subgraph.add_edge("tools", "agent")  # 循环
subgraph.add_edge("extract_answer", END)
```

**循环限制**: 最多 10 轮 ReAct 迭代（`recursion_limit=25` 在 config 中设置）

#### 并行路由

**route 节点**:
```python
def route(state: State):
    questions = state["rewrittenQuestions"]
    return [
        Send("process_question", {"question": q, "config": state["config"]})
        for q in questions
    ]
```

**Send() 机制**: LangGraph 自动并行执行所有子图，收集结果到 `aggregate` 节点。

#### Tool Artifact 机制

**知识库搜索工具**:
```python
@tool(response_format="content_and_artifact")
def knowledge_base_search(query: str) -> Tuple[str, List[dict]]:
    """检索知识库并返回 (content, artifact)。"""
    nodes = retriever.retrieve(query)

    # content: 用于 Agent 推理
    content = "\n".join([n.text for n in nodes])

    # artifact: 调试数据（传递给前端）
    artifact = [
        {"text": n.text[:500], "score": n.score, "source_file": n.metadata["file_name"]}
        for n in nodes
    ]

    return content, artifact
```

**传递到前端**: `aggregate` 节点收集所有 artifacts，存入 `state["debug_retrieved_chunks"]`，SSE 流式发送 `chunks` 事件。

#### Checkpointer

**MemorySaver**: 内存存储，不支持 `delete` 操作。

**重置对话**:
- ❌ 不能用 `/chat/reset` 删除 thread
- ✅ 客户端使用新的 `thread_id` 创建新对话

---

## 6. 多模态架构

### 6.1 层级节点存储

**设计**: Parent-Child 分离存储（已在 §3.2 详述）

### 6.2 图文提取流程

```
PDF → PyMuPDF 解析 → 提取图片 + 上下文文本 (page_text)
→ ImageProcessor (压缩 1024px / 去重 MD5) → VLM 摘要（Qwen-VL-Max）
→ MultimodalSplitter (父子节点生成) → (parent_nodes, child_nodes)
```

**Parent Node 结构**:
```python
{
    "id": "parent_abc123",
    "text": "<base64_image_1>\n\n上下文文本...\n\n<base64_image_2>",
    "metadata": {
        "file_name": "manual.pdf",
        "page": 12,
        "user_role": "teacher",
        "images": [
            {"base64": "...", "hash": "md5_hash", "type": "SCREENSHOT"},
            ...
        ]
    }
}
```

**Child Node 结构**:
```python
{
    "id": "child_xyz789",
    "text": "图片内容：系统登录界面，包含用户名和密码输入框，以及'登录'按钮。",
    "metadata": {
        "parent_id": "parent_abc123",
        "file_name": "manual.pdf",
        "page": 12,
        "user_role": "teacher",
        "image_type": "SCREENSHOT"
    }
}
```

### 6.3 VLM 处理

**3 种 VLM 用途**:

| 用途 | 模型 | 输入 | 输出 | 文件位置 |
|------|------|------|------|----------|
| **Embedding** | Qwen3-VL-Embedding | Image bytes | 2560-dim vector | `services/ingestion/app/components/providers/vlm.py` |
| **Summarization** | Qwen-VL-Max | Image bytes | 图片描述文本（中文） | `services/ingestion/app/components/providers/vlm.py` |
| **Multimodal LLM** | Qwen-VL-Plus | Image + Text | 操作指导（图文混合推理） | `services/inference/app/components/providers/qwen_vl_llm.py` |

**Embedding 示例**:
```python
from app.components.providers.vlm import QwenVLProvider

provider = QwenVLProvider()
vector = provider.encode_image(image_bytes)
# vector.shape = (2560,)
```

**Summarization 示例**:
```python
summary = provider.summarize_image(
    image_bytes,
    prompt="描述这张系统操作截图的内容，包括按钮、输入框和页面布局。"
)
# summary = "系统登录界面，包含用户名和密码输入框..."
```

### 6.4 角色过滤

**角色映射表**（已在 §3.2 详述）

**检索过滤实现**:
```python
# Qdrant filter
from qdrant_client.models import Filter, FieldCondition, MatchValue

if user_role is not None:
    # 非管理员：过滤 user_role
    filter = Filter(
        should=[
            FieldCondition(key="user_role", match=MatchValue(value=user_role)),
            FieldCondition(key="user_role", match=MatchValue(value="common"))
        ]
    )
else:
    # 管理员：无过滤
    filter = None

results = qdrant_client.search(
    collection_name=collection_name,
    query_vector=query_vector,
    query_filter=filter,
    limit=top_k
)
```

---

## 7. 配置与扩展

### 7.1 配置文件

**完整列表**:

| 文件 | 用途 | 说明 |
|------|------|------|
| `default.yaml` | 单实验配置（默认） | Baseline 配置，快速测试 |
| `ablation_grid.yaml` | 消融实验矩阵（多维度网格） | Chunking × Retrieval × Reranking 笛卡尔积 |
| `hierarchical_markdown.yaml` | 层级 Markdown 切分配置 | 父子节点生成，Auto-Merge retriever |
| `exp_semantic.yaml` | 语义切分实验预设 | Semantic chunking + breakpoint tuning |
| `exp_sentence.yaml` | 句子切分实验预设 | Sentence splitter + parent-child nodes |
| `best_retrieval.yaml` | 最优检索配置（基准） | Hybrid + Rerank + top_k=50 → 5 |

**配置示例** (`default.yaml`):
```yaml
experiment_id: "default"
experiment_description: "Default Configuration"

# Model Providers
llm_provider: "dashscope"
llm_model: "qwen-plus"
llm_temperature: 0.1
embedding_provider: "dashscope"
embedding_model: "text-embedding-v4"
embedding_dim: 1536

# Storage
qdrant_url: "http://localhost:6333"
mysql_url: "mysql+pymysql://rag_user:rag_password@localhost:3306/rag_db"

# Chunking
chunking_strategy: "fixed"
chunk_size_parent: 1024
chunk_size_child: 256
chunk_overlap: 50

# Retrieval
enable_hybrid: true
hybrid_alpha: 0.5
enable_rerank: true
retrieval_top_k: 50
rerank_top_k: 5

# Multimodal
enable_multimodal: false
user_role: null  # null = admin (sees all)
```

### 7.2 环境变量

**必需**:
- `DASHSCOPE_API_KEY`: DashScope API 密钥（LLM + Embedding + VLM）

**可选**:
- `QDRANT_URL`: Qdrant 连接 URL（默认 `http://localhost:6333`）
- `MYSQL_URL`: MySQL 连接串（默认 `mysql+pymysql://rag_user:rag_password@localhost:3306/rag_db`）
- `HF_ENDPOINT`: Hugging Face 镜像（中国区域：`hf-mirror.com`）

**`.env` 文件示例**:
```bash
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxx
QDRANT_URL=http://localhost:6333
MYSQL_URL=mysql+pymysql://rag_user:rag_password@localhost:3306/rag_db
HF_ENDPOINT=hf-mirror.com
```

### 7.3 扩展指南

**添加新 Chunker**:
```python
# 1. 实现基类
from rag_shared.core.types import BaseChunker

class MyChunker(BaseChunker):
    def chunk(self, documents):
        # 实现切片逻辑
        return nodes

# 2. 注册组件
from rag_shared.core.registry import ComponentRegistry

@ComponentRegistry.chunker("my_chunker")
class MyChunker(BaseChunker):
    ...

# 3. 配置中使用
# configs/my_config.yaml
chunking_strategy: "my_chunker"
```

**添加新 Embedding Provider**:
```python
# 1. 实现基类
from rag_shared.core.types import BaseEmbeddingProvider

class MyEmbedding(BaseEmbeddingProvider):
    def create_embedding_model(self, model_name, api_key, **kwargs):
        # 返回 LlamaIndex Embedding 对象
        return MyEmbeddingModel(...)

# 2. 注册组件
@ComponentRegistry.embedding_provider("my_embedding")
class MyEmbedding(BaseEmbeddingProvider):
    ...

# 3. 配置中使用
embedding_provider: "my_embedding"
embedding_model: "my-model-v1"
```

---

## 8. 开发参考

### 8.1 目录结构

```
shared/                          # 共享库 (零重型依赖)
├── pyproject.toml
└── rag_shared/
    ├── core/
    │   ├── types.py             # ABCs: 8 个基类 + ImageType enum
    │   └── registry.py          # ComponentRegistry (8 types)
    ├── config/
    │   └── experiment.py        # ExperimentConfig + ExperimentGrid
    ├── schemas/
    │   ├── ingestion.py         # Ingestion API schemas
    │   ├── inference.py         # Inference API schemas
    │   └── multimodal.py        # ImageData, MultimodalChunk, role schemas
    ├── utils/
    │   ├── logger.py            # loguru logger
    │   └── role_mapper.py       # Role extraction from filename

services/ingestion/              # 数据接入服务 (Port 8001)
├── pyproject.toml               # numpy>=2.0, llama-index, pymupdf
├── Dockerfile
└── app/
    ├── main.py                  # FastAPI + lifespan
    ├── config.py                # ServiceSettings (data partition paths)
    ├── api/
    │   └── routes.py            # REST API (7 endpoints)
    ├── services/
    │   └── ingestion.py         # IngestionService (chunking + embedding)
    ├── storage/
    │   ├── vectordb.py          # VectorStoreManager (Qdrant dual-mode)
    │   └── metadata.py          # DatabaseManager (SQLite)
    ├── components/
    │   ├── chunkers/            # fixed, recursive, sentence, semantic, multimodal
    │   ├── providers/           # dashscope, bgem3 (jieba), vlm (Qwen-VL)
    │   └── processors/          # image.py (compression, dedup)
    ├── parsing/
    │   ├── parser.py            # pypdf + docx2txt
    │   ├── multimodal_parser.py # PyMuPDF image extraction
    │   └── cleaner.py           # PolicyCleaner (TOC removal)
    └── tests/
        ├── test_multimodal_parser.py      # 多模态解析器单元测试
        ├── test_all_manuals.py            # 批量手册测试
        ├── scripts/                       # 功能测试脚本
        │   ├── test_cleaner.py
        │   ├── test_sentence_chunker.py
        │   └── test_vectorization.py
        └── datas/                         # 测试数据输出
            ├── cleaner_test_results/      # 清洗器测试
            │   └── policy/
            ├── sentence_chunker_test_results/  # 切分器测试
            │   └── policy/
            └── multimodal_parser_test/    # 多模态解析测试
                ├── 4-1/extracted_images/
                ├── 4-2/extracted_images/
                ├── 4-3/extracted_images/
                └── 4-4/extracted_images/

services/inference/              # 推理与 Agent 服务 (Port 8002)
├── pyproject.toml               # numpy<2.0, langgraph, sse-starlette
├── Dockerfile
└── app/
    ├── main.py                  # FastAPI + lifespan
    ├── config.py                # ServiceSettings
    ├── api/
    │   └── routes.py            # SSE streaming (5 endpoints)
    ├── agent/
    │   ├── workflow.py          # create_graph() (main + subgraph)
    │   ├── state.py             # State + AgentState
    │   ├── nodes.py             # 5 nodes (summarize, rewrite, route, aggregate, extract)
    │   ├── tools.py             # knowledge_base_search (Tool Artifact)
    │   └── prompts.py           # System prompts
    ├── services/
    │   ├── retrieval.py         # RetrievalService (hybrid/rerank)
    │   └── multimodal_retrieval.py  # MultimodalRetrievalService
    ├── storage/
    │   ├── vectordb.py          # VectorStoreManager (read-only)
    │   └── mysql_client.py      # MySQLClient (parent node lookup)
    ├── components/
    │   └── providers/           # dashscope, bgem3, qwen_vl_llm
    └── tests/
        └── datas/               # 测试数据（规划中）

services/gateway/                # UI 网关 (Port 7860)
├── pyproject.toml               # gradio, httpx, httpx-sse
├── Dockerfile
└── app/
    ├── main.py                  # Gradio launch
    ├── config.py                # ServiceSettings (backend URLs)
    ├── clients/
    │   ├── ingestion.py         # httpx client (sync)
    │   └── inference.py         # httpx-sse client (streaming)
    ├── ui/
    │   └── app.py               # Gradio UI (3 tabs)
    └── tests/
        ├── poc_multimodal/      # POC 测试套件
        │   ├── poc_test_dashscope_multimodal.py
        │   ├── poc_test_pdf_image_extraction.py
        │   ├── poc_test_qdrant_multimodal.py
        │   ├── POC_README.md
        │   └── QUICKSTART.md
        └── datas/               # 测试数据
            ├── test_images/     # 输入：测试截图
            ├── extracted_images/  # 输出：PDF 提取图片
            └── poc_results/     # 输出：POC 测试报告

cli/                             # 消融实验 CLI
├── pyproject.toml               # httpx, pandas, tqdm
└── rag_cli/
    ├── main.py                  # CLI entry point (rag-eval)
    └── clients/                 # Sync httpx clients

configs/                         # 配置文件（6 个 YAML）
├── default.yaml                 # 单实验默认配置
├── ablation_grid.yaml           # 消融实验矩阵
├── hierarchical_markdown.yaml   # 层级切分配置
├── exp_semantic.yaml            # 语义切分实验
├── exp_sentence.yaml            # 句子切分实验
└── best_retrieval.yaml          # 最优检索配置

scripts/                         # 运维脚本
├── init_mysql.sql               # MySQL 初始化 SQL
└── migrate_multimodal_schema.sql  # 多模态 schema 迁移

data/                            # 运行时数据（gitignored）
├── vectordb/                    # Qdrant 本地存储
├── metadata.db                  # SQLite 元数据
├── mysql/                       # MySQL 数据目录
├── reports/                     # 评测报告
└── uploads/                     # 用户上传文件

docs/                            # 文档
├── multimodal-architecture-implementation.md
├── multimodal-changes-verification-checklist.md
└── agent-learning/              # Agent 学习材料
    └── cases/                   # 经验案例库
```

### 8.2 测试组织规范

#### 通用原则

1. **输入数据 vs 测试数据分离**：
   - 实际输入数据 → `services/ingestion/data/`
   - 测试和验证数据 → `services/*/tests/datas/`

2. **POC 测试放置原则**：
   - **Gateway** 负责端到端测试（用户视角）
   - POC 测试模拟用户完整使用流程，放在 `services/gateway/tests/poc_multimodal/`
   - 输入数据可复用 `services/ingestion/data/manual/` 中的手册

3. **测试数据命名规范**：
   - 功能测试输出：`{feature}_test_results/`
   - 单元测试输出：`{feature}_test/{file_id}/`
   - POC 测试数据：`poc_multimodal/`

#### 测试数据存放规则

| 数据类型 | 存放位置 | 示例 |
|---------|---------|------|
| **输入数据（实际）** | `services/ingestion/data/{category}/` | `data/manual/4-1.pdf` |
| **输入数据（测试专用）** | `tests/datas/test_{input}/` | `tests/datas/test_images/` |
| **功能测试输出** | `tests/datas/{feature}_test_results/` | `cleaner_test_results/policy/` |
| **单元测试输出** | `tests/datas/{feature}_test/{id}/` | `multimodal_parser_test/4-1/` |
| **POC 测试输出** | `tests/datas/poc_results/` | `poc_results/poc1_report.json` |

#### 文件命名约定

- 单元测试：`test_*.py`（测试单个模块/函数）
- 功能测试：`test_*.py`（测试完整功能流程）
- POC 测试：`poc_test_*.py`（验证概念可行性）
- 测试结果目录：`{feature}_test_results/` 或 `{feature}_test/`

### 8.3 数据库 Schema

#### MySQL - parent_nodes 表

```sql
CREATE TABLE IF NOT EXISTS parent_nodes (
    id VARCHAR(255) PRIMARY KEY,
    collection_name VARCHAR(255) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    text LONGTEXT NOT NULL,              -- 图片上下文文本 + base64 编码图片
    metadata JSON,                        -- {user_role, image_type, images: [...]}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_collection (collection_name),
    INDEX idx_file (file_name),
    INDEX idx_collection_file (collection_name, file_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**字段说明**:
- `id`: Parent node UUID
- `collection_name`: Qdrant collection 名称
- `file_name`: 源文件名（如 `4-1 指导老师操作手册.pdf`）
- `text`: 上下文文本 + base64 图片（用于 VLM 推理）
- `metadata`: JSON 字段
  - `user_role`: 角色标识（`teacher`, `student`, `reviewer`, `defense_committee`, `common`）
  - `page`: 页码
  - `images`: 图片列表 `[{"base64": "...", "hash": "...", "type": "SCREENSHOT"}, ...]`

#### SQLite - metadata.db

**tables**:
1. `collections`: Collection 元数据
   - `name`: Collection 名称
   - `created_at`: 创建时间

2. `documents`: 文档元数据
   - `collection_name`: Collection 名称
   - `file_name`: 文件名
   - `indexed_at`: 入库时间

**用途**: 快速查询文件列表、集合信息，避免频繁查询 Qdrant。

### 8.4 关键文件位置

**快速索引表**:

| 功能 | 文件位置 |
|------|----------|
| **ComponentRegistry** | `shared/rag_shared/core/registry.py` |
| **Abstract Base Classes** | `shared/rag_shared/core/types.py` |
| **ExperimentConfig** | `shared/rag_shared/config/experiment.py` |
| **Role Mapper** | `shared/rag_shared/utils/role_mapper.py` |
| **Ingestion API** | `services/ingestion/app/api/routes.py` |
| **Inference API** | `services/inference/app/api/routes.py` |
| **IngestionService** | `services/ingestion/app/services/ingestion.py` |
| **RetrievalService** | `services/inference/app/services/retrieval.py` |
| **MultimodalRetrievalService** | `services/inference/app/services/multimodal_retrieval.py` |
| **LangGraph Workflow** | `services/inference/app/agent/workflow.py` |
| **LangGraph Nodes** | `services/inference/app/agent/nodes.py` |
| **LangGraph Tools** | `services/inference/app/agent/tools.py` |
| **PolicyCleaner** | `services/ingestion/app/parsing/cleaner.py` |
| **Multimodal Parser** | `services/ingestion/app/parsing/multimodal_parser.py` |
| **Jieba Sparse Vectors** | `services/ingestion/app/components/providers/bgem3.py` |
| **VLM Provider** | `services/ingestion/app/components/providers/vlm.py` |
| **Multimodal Chunker** | `services/ingestion/app/components/chunkers/multimodal.py` |
| **VectorStoreManager (Ingestion)** | `services/ingestion/app/storage/vectordb.py` |
| **VectorStoreManager (Inference)** | `services/inference/app/storage/vectordb.py` |
| **MySQLClient** | `services/inference/app/storage/mysql_client.py` |
| **Gateway UI** | `services/gateway/app/ui/app.py` |
| **MySQL Init Script** | `scripts/init_mysql.sql` |

---

## 9. 运维指南

### 9.1 部署

#### Docker Compose（生产推荐）

```bash
# 启动全部服务
docker compose up -d

# 查看日志
docker compose logs -f ingestion
docker compose logs -f inference
docker compose logs -f gateway

# 停止服务
docker compose down

# 清理数据（危险操作）
docker compose down -v
```

#### 独立服务部署

```bash
# Ingestion Service
cd services/ingestion
poetry install
poetry run python -m app.main

# Inference Service
cd services/inference
poetry install
poetry run python -m app.main

# Gateway Service
cd services/gateway
poetry install
poetry run python -m app.main
```

#### 环境变量检查清单

- [ ] `DASHSCOPE_API_KEY` 已设置
- [ ] `QDRANT_URL` 正确（Docker: `http://qdrant:6333`, 本地: `http://localhost:6333`）
- [ ] `MYSQL_URL` 正确（Docker: `mysql://rag_user:rag_password@mysql:3306/rag_db`）
- [ ] `HF_ENDPOINT` 设置为 `hf-mirror.com`（中国区域）
- [ ] MySQL 初始化脚本已执行（`scripts/init_mysql.sql`）

### 9.2 监控

#### 健康检查

```bash
# Ingestion Service
curl http://localhost:8001/health

# Inference Service
curl http://localhost:8002/health

# Qdrant
curl http://localhost:6333/health

# MySQL
mysql -h localhost -u rag_user -prag_password -e "SELECT 1"
```

#### 日志位置

- **Docker Compose**: `docker compose logs -f {service}`
- **本地开发**: 标准输出 (stdout)
- **Gateway UI**: Gradio 自动日志输出

#### 性能指标

| 指标 | 正常范围 | 监控方法 |
|------|----------|----------|
| Ingestion API 响应时间 | <5s (单文档) | `/docs` Swagger UI |
| Inference API 首 token 时间 | <2s | SSE 流式监控 |
| Qdrant 查询延迟 | <500ms | Qdrant UI Dashboard |
| MySQL 查询延迟 | <100ms | MySQL slow query log |
| 内存占用（Ingestion） | <2GB | `docker stats` |
| 内存占用（Inference） | <4GB | `docker stats` |

### 9.3 故障排查（Troubleshooting）

#### Q1: numpy 版本冲突

**症状**: Ingestion 或 Inference 启动报 `numpy version error`

**原因**:
- Ingestion 需要 `numpy>=2.0` (MinerU 依赖)
- Inference 需要 `numpy<2.0` (LangChain 依赖)

**解决**:
1. 检查是否在正确的 Poetry 环境：
   ```bash
   cd services/ingestion && poetry env info
   cd services/inference && poetry env info
   ```
2. 确认独立安装：
   ```bash
   cd services/ingestion && poetry install
   cd services/inference && poetry install
   ```
3. 清理缓存重装：
   ```bash
   cd services/ingestion && poetry env remove python && poetry install
   ```

#### Q2: Qdrant 连接失败

**症状**: 服务启动报 `Cannot connect to Qdrant`

**原因**: 双模式配置错误（URL vs 本地路径）

**解决**:
1. **Docker Compose 模式**:
   - 配置：`qdrant_url: "http://qdrant:6333"`（使用 Docker 网络内部名称）
   - 验证：`docker compose exec ingestion curl http://qdrant:6333/health`

2. **本地开发模式**:
   - 配置：`qdrant_url: "http://localhost:6333"` 或 `qdrant_path: "data/vectordb"`
   - 验证：`curl http://localhost:6333/health`

3. **检查 Qdrant 是否启动**:
   ```bash
   docker ps | grep qdrant
   # 或
   curl http://localhost:6333/dashboard
   ```

#### Q3: MySQL 父节点查询失败

**症状**: 多模态检索返回空结果或报错 `Table 'parent_nodes' doesn't exist`

**原因**: MySQL 未初始化或连接串错误

**解决**:
1. **检查 MySQL 初始化**:
   ```bash
   # 进入 MySQL 容器
   docker compose exec mysql mysql -u rag_user -prag_password rag_db

   # 检查表是否存在
   SHOW TABLES;
   # 应包含 parent_nodes 表
   ```

2. **手动执行初始化脚本**:
   ```bash
   docker compose exec mysql mysql -u rag_user -prag_password rag_db < scripts/init_mysql.sql
   ```

3. **验证连接串**:
   ```bash
   # .env 文件
   MYSQL_URL=mysql+pymysql://rag_user:rag_password@localhost:3306/rag_db

   # Docker Compose 内部
   MYSQL_URL=mysql+pymysql://rag_user:rag_password@mysql:3306/rag_db
   ```

#### Q4: MultimodalChunker 返回 list 而非 tuple

**症状**: 入库报错 `Expected tuple, got list`

**原因**: Chunker 未正确返回 `(parent_nodes, child_nodes)` tuple

**解决**:
1. **检查 Chunker 实现**:
   ```python
   # services/ingestion/app/components/chunkers/multimodal.py
   def chunk(self, documents):
       # ...
       return (parent_nodes, child_nodes)  # 必须是 tuple
   ```

2. **检查配置**:
   ```yaml
   # configs/*.yaml
   enable_multimodal: true  # 确保启用多模态
   chunking_strategy: "multimodal"  # 使用 multimodal chunker
   ```

3. **调试入库服务**:
   ```python
   # services/ingestion/app/services/ingestion.py
   result = chunker.chunk(documents)
   print(type(result))  # 应输出 <class 'tuple'>
   print(isinstance(result, tuple))  # 应输出 True
   ```

#### Q5: LangGraph 对话无法重置

**症状**: 调用 `/chat/reset` 后对话历史仍存在

**原因**: `MemorySaver` 不支持 `delete` 操作

**解决**:
1. **使用新 thread_id** (推荐):
   ```python
   # 客户端
   import uuid
   new_thread_id = str(uuid.uuid4())

   response = requests.post("/chat/stream", json={
       "message": "新对话",
       "thread_id": new_thread_id  # 使用新 ID
   })
   ```

2. **切换到持久化 Checkpointer**（可选）:
   ```python
   # services/inference/app/agent/workflow.py
   from langgraph.checkpoint.sqlite import SqliteSaver

   checkpointer = SqliteSaver("data/checkpoints.db")
   graph = graph.compile(checkpointer=checkpointer)

   # 支持删除
   checkpointer.delete(thread_id)
   ```

#### Q6: 角色过滤无效

**症状**: 用户看到不应该看到的内容

**原因**: 文件名未包含角色关键词，或 `user_role` 参数未传递

**解决**:
1. **检查文件名规范**:
   ```
   ✅ 正确: "4-1 郑州大学毕业论文系统指导老师操作手册.pdf" → teacher
   ✅ 正确: "4-4 学生操作手册.pdf" → student
   ❌ 错误: "manual.pdf" → common（所有角色可见）
   ```

2. **验证 `user_role` 参数**:
   ```python
   # API 请求
   {
       "message": "如何提交论文？",
       "config": {
           "collection_name": "manual_test",
           "user_role": "student"  # 确保传递
       }
   }
   ```

3. **检查 node metadata**:
   ```python
   # Qdrant 查询
   from qdrant_client import QdrantClient

   client = QdrantClient("http://localhost:6333")
   points = client.scroll(collection_name="manual_test", limit=10)

   for point in points[0]:
       print(point.payload.get("user_role"))  # 应有 teacher/student/common
   ```

4. **调试角色映射**:
   ```python
   from rag_shared.utils.role_mapper import extract_role_from_filename

   filename = "4-1 郑州大学毕业论文系统指导老师操作手册.pdf"
   role = extract_role_from_filename(filename)
   print(role)  # 应输出 "teacher"
   ```

#### Q7: SSE 流式传输中断

**症状**: Gateway UI 显示部分 token 后停止

**原因**:
- 网络超时
- LangGraph Agent 超时（`recursion_limit` 达到）
- Inference Service 崩溃

**解决**:
1. **检查 Inference Service 日志**:
   ```bash
   docker compose logs -f inference
   # 查找 traceback 或 error
   ```

2. **调整 recursion_limit**:
   ```python
   # services/inference/app/api/routes.py
   lc_config = {
       "configurable": {"thread_id": thread_id},
       "recursion_limit": 50,  # 增加到 50
   }
   ```

3. **测试 SSE 连接**:
   ```bash
   curl -N -H "Content-Type: application/json" \
     -d '{"message": "测试", "config": {}}' \
     http://localhost:8002/api/v1/chat/stream
   ```

#### Q8: 稀疏向量搜索结果差

**症状**: 混合检索效果不如纯 dense embedding

**原因**:
- jieba 分词不准确
- stopwords 过滤过度
- `hybrid_alpha` 权重不合理

**解决**:
1. **调整 hybrid_alpha**:
   ```yaml
   # configs/*.yaml
   hybrid_alpha: 0.3  # 降低稀疏权重（0=纯dense, 1=纯sparse）
   ```

2. **自定义 stopwords**:
   ```python
   # services/ingestion/app/components/providers/bgem3.py
   _STOPWORDS = frozenset({
       "的", "了", "在", "是", ...  # 根据业务调整
   })
   ```

3. **禁用稀疏向量**（回退到纯 dense）:
   ```yaml
   enable_hybrid: false
   ```

### 9.4 注意事项

#### ⚠️ 关键警告

**numpy 版本隔离**:
- Ingestion: `numpy>=2.0` (MinerU)
- Inference: `numpy<2.0` (LangChain)
- **禁止共享环境**，必须独立 Poetry 环境

**ingestion_fingerprint 限制**:
- ❌ **不包含**稀疏模型信息（bgem3 → jieba）
- ✅ **包含**多模态参数（`enable_multimodal=True` 时）
- **改变稀疏模型需手动删除 collection**:
  ```bash
  curl -X DELETE http://localhost:6333/collections/{collection_name}
  ```

**Docker 网络配置**:
- Docker Compose 内部：使用服务名（`qdrant`, `mysql`）
- 宿主机访问：使用 `localhost`
- **混用会导致连接失败**

#### ⚙️ 配置说明

**VectorStoreManager 双模式**:
- 优先使用 `qdrant_url`（HTTP，Docker 推荐）
- Fallback 到 `qdrant_path`（本地路径，开发调试）
- **生产环境禁用 qdrant_path**

**MySQL 初始化**:
- Docker Compose：自动执行 `scripts/init_mysql.sql`
- 本地开发：手动执行 `mysql < scripts/init_mysql.sql`

**运行时数据**:
- 位置：`data/` 目录（gitignored）
- 内容：`vectordb/`, `metadata.db`, `mysql/`, `reports/`, `uploads/`
- **备份策略**：定期备份 MySQL + Qdrant collections

#### 📋 架构细节

**MultimodalChunker 返回值**:
- ✅ 返回：`(parent_nodes, child_nodes)` tuple
- ❌ 其他 Chunker 返回：`List[Node]`
- **检测机制**：`isinstance(result, tuple)`

**角色过滤**:
- `user_role=None`: 管理员（查看全部）
- `user_role="teacher"`: 过滤角色（仅查看 teacher + common）
- `user_role="common"`: 所有角色可见

**Auto-Merge 无效**:
- 当前为平面节点（Flat nodes）
- 未使用 `HierarchicalNodeParser`
- **Sentence chunker 的父子节点用于检索融合，非层级关系**

**中国区域模型下载**:
```bash
export HF_ENDPOINT=hf-mirror.com
```

**服务初始化**:
- Docker Compose: `docker compose up -d`
- 本地开发: `poetry run python -m app.main`（各服务独立启动）

---

## 10. Agent Learning

当用户完成一个工作后说**"总结经验"**或**"记录这次工作"**时，生成简洁但结构化的经验记录，保存到 `docs/agent-learning/cases/YYYY-MM-DD_工作名.md`。

**关键原则**：
- **问题**要说明"影响"（对下游流程的具体影响）
- **方案**要列出编号的"核心规则"（可直接转换为代码逻辑）
- **标准**要用表格 + 说明列（解释指标含义和计算方式）
- **适用**要结构化描述文档特征 + 解释"为什么适用"
- **代码**要包含文件位置、关键类/方法、验证工具

**目的**：为未来 Agent 化积累可直接应用的"学习材料"（问题识别、解决方案、评估标准）。

---

## 附录：版本历史

**当前版本**: v2.1 (2026-02-27)

**更新内容**:
- ✅ 补充 `/multimodal/chat` 端点文档
- ✅ 补充 MySQL schema 文档
- ✅ 补充 PolicyCleaner 实现细节（TOC 清理逻辑）
- ✅ 补充稀疏向量技术细节（jieba + MD5 + BM25）
- ✅ 补充 LangGraph 子图结构（process_question ReAct loop）
- ✅ 补充完整配置文件列表（6 个 YAML）
- ✅ 补充多模态配置参数文档
- ✅ 重组 Important Notes（按关注级别分类）
- ✅ 新增 Troubleshooting 章节（8 个常见问题）
- ✅ 新增数据流图（3 个关键流程）
- ✅ 新增测试组织规范
- ✅ 优化文档结构（11 章节，清晰分层）

---

**文档最后更新**: 2026-02-27
**文档版本**: v2.1
**文档长度**: ~1050 行
