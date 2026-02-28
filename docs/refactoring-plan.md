# 多模态 RAG 系统 — 微服务架构重构计划

## Context

当前系统存在以下架构问题：
1. **职责边界模糊**：Ingestion 和 Inference 都直接操作 Qdrant，embedding 策略分散
2. **数据存储耦合**：微服务本地存储文件和图片，不利于横向扩展
3. **shared 库不必要**：分析发现 types/registry/config 只有 Indexing 真正需要，schemas 可各服务自定义
4. **缺少编排层**：Gateway 仅做 UI 代理，没有真正的 RAG 流程编排
5. **测试分散**：测试代码散落在各服务目录中，没有集中管理

**目标**：重构为 4 个职责纯粹的微服务（无 shared 库） + 外部存储，服务间契约通过 HTTP API 定义。

---

## 1. 目标架构

```
                    ┌──────────────────────────┐
                    │   Orchestrator Service   │  Port 8000
                    │   (FastAPI)              │
                    │                          │
                    │  - 用户入口 (文件上传/查询) │
                    │  - 文件存储到 MinIO       │
                    │  - 编排 Indexing + Agent   │
                    │  - 不存储任何业务数据      │
                    └─────────┬────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
          ┌──────────────────┐  ┌──────────────────┐
          │ Indexing Service  │←→│  Agent Service   │
          │ (Port 8001)      │  │  (Port 8002)     │
          │ LlamaIndex       │  │  LangGraph       │
          │                  │  │                  │
          │ - PDF 解析/清洗   │  │ - LLM 对话推理   │
          │ - 切片/Embedding  │  │ - VLM 图像分析   │
          │ - 向量写入 Qdrant │  │ - ReAct 工作流   │
          │ - 向量检索 Qdrant │  │ - SSE 流式输出   │
          │ - Reranker       │  │ - 不直接访问 DB   │
          │ - 父节点读写MySQL │  │                  │
          └────────┬─────────┘  └──────────────────┘
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
       Qdrant    MySQL    MinIO
       (向量)   (父节点)  (文件/图片)

  ┌──────────────────────────────────────────────────────┐
  │ Testing Service (Port 8003)                          │
  │ - 调用 Orchestrator/Indexing/Agent API 执行功能测试   │
  │ - 测试数据管理                                       │
  │ - 测试结果存储与报告                                  │
  └──────────────────────────────────────────────────────┘

  双向调用（不同流程，无循环）:
  ┌─────────────────────────────────────────────────┐
  │ 入库流程: Indexing → Agent /api/v1/vlm/analyze  │
  │          (请求 VLM 生成截图摘要"小作文")          │
  │                                                 │
  │ 查询流程: Agent → Indexing /api/v1/retrieve     │
  │          (ReAct 工具调用检索知识库)               │
  └─────────────────────────────────────────────────┘
```

### 1.1 核心原则

| 原则 | 说明 |
|------|------|
| **无 shared 库** | 删除 `shared/` 目录，服务间契约通过 HTTP API 定义，不通过 Python 包共享 |
| **微服务无状态** | 4 个微服务均不在本地存储数据/文件，全部交给 Docker 容器中的外部存储 |
| **Embedding 一致性** | 向量写入和读取都由 Indexing Service 负责，天然保证策略一致 |
| **Agent = LLM/VLM 能力中心** | Agent 对外提供 LLM 推理 + VLM 分析能力，供 Indexing 和 Orchestrator 调用 |
| **测试集中管理** | 所有功能测试、集成测试、测试数据和结果统一在 Testing Service |
| **现有逻辑保留** | 政策类文档的 PolicyCleaner、各种 Chunker、jieba 稀疏向量等逻辑迁移后保留不变 |

### 1.2 存储职责

| 存储 | 容器 | 职责 | 访问者 |
|------|------|------|--------|
| **MinIO** | Docker | 原始 PDF 文件、提取的图片 | Orchestrator(写)、Indexing(读写) |
| **Qdrant** | Docker | 文本向量、稀疏向量（未来：图像向量） | Indexing(读写) |
| **MySQL** | Docker | parent_nodes、collections、documents 元数据 | Indexing(读写) |

> SQLite 移除，元数据统一存入 MySQL。

### 1.3 shared 库处理方案

| 原 shared 模块 | 迁移目标 | 原因 |
|---------------|---------|------|
| `core/types.py` (ABCs) | → Indexing `app/core/types.py` | 只有 Indexing 有 chunker/provider 实现 |
| `core/registry.py` | → Indexing `app/core/registry.py` | 只有 Indexing 注册和查询组件 |
| `config/experiment.py` | → Indexing `app/config/experiment.py` | Indexing 是主要消费者；其他服务通过 API 传 dict |
| `utils/role_mapper.py` | → Indexing `app/utils/role_mapper.py` | 只在文件解析时使用 |
| `utils/logger.py` | 各服务自定义 | 16 行代码，各服务独立配置 |
| `schemas/*.py` | 各服务自定义 schemas | 每个服务定义自己的请求/响应模型 |

---

## 2. 服务详细设计

### 2.1 Orchestrator Service (Port 8000)

**职责**：用户入口 + 文件中转到 MinIO + 流程编排

#### API 端点

| 端点 | 方法 | 功能 | 流程 |
|------|------|------|------|
| `/api/v1/upload` | POST | 上传文件 | 接收文件 → 存入 MinIO → 调用 Indexing `/index` |
| `/api/v1/chat` | POST | 文本对话 | 接收 query → 转发 Agent `/chat` → 透传 SSE |
| `/api/v1/collections` | GET | 列出集合 | 代理到 Indexing |
| `/api/v1/collections/{name}/files` | GET | 列出文件 | 代理到 Indexing |
| `/api/v1/documents/{collection}/{file}` | DELETE | 删除文档 | 调用 Indexing + 清理 MinIO |
| `/health` | GET | 健康检查 | 检查自身 + 下游服务 |

#### 文件上传流程

```
1. 用户 POST multipart/form-data (file + config JSON)
2. Orchestrator 存入 MinIO:
   - bucket: "raw-documents"
   - key: "{collection_name}/{filename}"
3. Orchestrator 调用 Indexing:
   POST /api/v1/index
   {
     "minio_bucket": "raw-documents",
     "minio_key": "{collection_name}/{filename}",
     "filename": "4-2 学生操作手册.pdf",
     "config": { ... }
   }
4. Indexing 从 MinIO 下载 → 解析 → 向量化 → 存储
5. 返回入库结果给用户
```

#### 对话流程

```
1. 用户 POST { message, config, thread_id }
2. Orchestrator 转发到 Agent:
   POST /api/v1/chat { message, config, thread_id }
3. Agent 内部 ReAct 循环:
   需要检索时 → 调用 Indexing /api/v1/retrieve
4. Orchestrator 透传 SSE 流给用户
```

#### 依赖

```toml
[tool.poetry.dependencies]
python = "^3.10"
fastapi = ">=0.100"
uvicorn = ">=0.20"
httpx = ">=0.25"
httpx-sse = ">=0.4"
minio = ">=7.2"
```

---

### 2.2 Indexing Service (Port 8001)

**职责**：文档全生命周期管理 + 向量读写（LlamaIndex 框架）

#### API 端点

| 端点 | 方法 | 功能 | 调用者 |
|------|------|------|--------|
| `/api/v1/index` | POST | MinIO 文件 → 解析 → 切片 → 向量化 → 存储 | Orchestrator |
| `/api/v1/retrieve` | POST | 文本检索（Dense + Sparse + Rerank） | Agent |
| `/api/v1/collections` | GET | 列出 Qdrant collections | Orchestrator |
| `/api/v1/collections/{name}/files` | GET | 列出 collection 中文件 | Orchestrator |
| `/api/v1/documents/{collection}/{filename}` | DELETE | 删除文档向量和元数据 | Orchestrator |
| `/health` | GET | 健康检查 | 所有 |

#### 入库流程 (`POST /api/v1/index`)

```
1. 从 MinIO 下载文件
2. 解析: PDF → pypdf/PyMuPDF, DOCX → docx2txt
3. 清洗: PolicyCleaner / ManualCleaner（路由: get_cleaner_for_file）
4. 切片: fixed / recursive / sentence / semantic
   通过 ComponentRegistry.get_chunker(strategy)
5. [多模态] VLM 摘要 — 调用 Agent:
   POST Agent /api/v1/vlm/batch-analyze
   → 发送截图 + 上下文 ← 返回"小作文"
6. Embedding:
   - 文本: DashScope text-embedding-v4 (1536-dim)
   - 稀疏: jieba BM25
   - [多模态] 图像: Qwen3-VL-Embedding (2560-dim)
7. 存储:
   - 子节点 → Qdrant
   - 父节点 → MySQL parent_nodes
   - 文档元数据 → MySQL documents
   - [多模态] 截图 → MinIO extracted-images
```

#### 检索流程 (`POST /api/v1/retrieve`)

```python
# 请求
{"query": "导师一直没审核我的任务书怎么办？", "config": {...}, "top_k": 5}

# 响应
{
    "nodes": [
        {
            "text": "任务书提交后，指导老师需在系统中审核...",
            "score": 0.92,
            "source_file": "4-2 学生操作手册.pdf",
            "page": 8,
            "node_type": "text",
            "metadata": {...}
        }
    ]
}
```

#### 从 shared 迁入的模块

| 模块 | 原位置 | 新位置 |
|------|--------|--------|
| ABCs + ImageType | `shared/rag_shared/core/types.py` | `services/indexing/app/core/types.py` |
| ComponentRegistry | `shared/rag_shared/core/registry.py` | `services/indexing/app/core/registry.py` |
| ExperimentConfig | `shared/rag_shared/config/experiment.py` | `services/indexing/app/config/experiment.py` |
| role_mapper | `shared/rag_shared/utils/role_mapper.py` | `services/indexing/app/utils/role_mapper.py` |

#### 从原 ingestion 迁入（逻辑不变）

| 模块 | 说明 |
|------|------|
| PolicyCleaner, ManualCleaner | 文档清洗，完全保留 |
| FixedChunker, RecursiveChunker, SentenceChunker, SemanticChunker | 切片策略，完全保留 |
| DashScope Provider | Embedding/Reranker，完全保留 |
| Jieba Sparse (bgem3.py) | 稀疏向量，完全保留 |

#### 从原 inference 迁入

| 模块 | 说明 |
|------|------|
| RetrievalService | 检索逻辑迁入（Dense+Sparse+Rerank） |
| VectorStoreManager | 合并读写功能为一个 |

#### 依赖

```toml
[tool.poetry.dependencies]
python = "^3.10"
numpy = ">=2.0"
fastapi = ">=0.100"
uvicorn = ">=0.20"
llama-index = ">=0.11"
pymupdf = ">=1.23"
jieba = ">=0.42"
minio = ">=7.2"
pymysql = ">=1.1"
sqlalchemy = ">=2.0"
httpx = ">=0.25"            # 调用 Agent VLM API
```

---

### 2.3 Agent Service (Port 8002)

**职责**：LLM/VLM 能力中心（LangGraph 框架），不直接访问任何数据库

#### API 端点

| 端点 | 方法 | 功能 | 调用者 |
|------|------|------|--------|
| `/api/v1/chat` | POST | SSE 流式对话（ReAct Agent 工作流） | Orchestrator |
| `/api/v1/chat/reset` | POST | 重置对话（生成新 thread_id） | Orchestrator |
| `/api/v1/vlm/analyze` | POST | VLM 单图分析（生成截图摘要） | Indexing |
| `/api/v1/vlm/batch-analyze` | POST | VLM 批量分析 | Indexing |
| `/health` | GET | 健康检查 | 所有 |

#### VLM API（供 Indexing 入库时调用）

```python
# POST /api/v1/vlm/analyze
{
    "image_base64": "iVBORw0KGgo...",
    "image_type": "screenshot",
    "surrounding_text": "点击提交按钮...",
    "prompt_template": null
}
# → {"summary": "系统登录界面，包含...", "model": "qwen-vl-max", "tokens_used": 342}

# POST /api/v1/vlm/batch-analyze
{
    "images": [
        {"image_base64": "...", "image_type": "screenshot", "surrounding_text": "..."},
        ...
    ]
}
# → {"results": [{"summary": "...", "tokens_used": 342}, ...], "total_tokens": 598}
```

#### LangGraph 工作流（保留现有结构）

```
User Query → summarize → analyze_rewrite → route
                                            ├─ process_question (子图 1)
                                            ├─ process_question (子图 2)
                                            └─ ...
                                          → aggregate → SSE Response
```

#### 关键变更：Tool 改为 HTTP 调用

```python
@tool(response_format="content_and_artifact")
def knowledge_base_search(query: str) -> Tuple[str, List[dict]]:
    """检索知识库 — 调用 Indexing Service API。"""
    response = httpx.post(
        f"{INDEXING_SERVICE_URL}/api/v1/retrieve",
        json={"query": query, "config": current_config, "top_k": 5},
        timeout=30,
    )
    nodes = response.json()["nodes"]
    content = "\n".join([n["text"] for n in nodes])
    artifact = [{"text": n["text"][:500], "score": n["score"], "source_file": n["source_file"]} for n in nodes]
    return content, artifact
```

#### 从原 inference 迁入

| 模块 | 说明 |
|------|------|
| workflow.py, state.py, nodes.py, prompts.py | LangGraph 工作流，保留 |
| SSE 流式输出 | astream_events 逻辑，保留 |
| QwenVLLLMProvider | 多模态 LLM 调用，保留 |

#### 从原 ingestion 迁入

| 模块 | 说明 |
|------|------|
| DashScopeVLMProvider (vlm.py) | VLM 摘要生成，**迁移到 Agent** |

#### 移除（职责转移到 Indexing）

- RetrievalService, VectorStoreManager, MySQLClient, bgem3.py

#### 依赖

```toml
[tool.poetry.dependencies]
python = "^3.10"
numpy = "<2.0"
fastapi = ">=0.100"
uvicorn = ">=0.20"
langgraph = ">=0.2"
langchain = ">=0.3"
langchain-community = ">=0.3"
sse-starlette = ">=1.6"
httpx = ">=0.25"
dashscope = ">=1.0"
```

---

### 2.4 Testing Service (Port 8003)

**职责**：集中管理所有功能测试、集成测试、测试数据和测试结果

#### 设计理念

- **不包含生产代码**：纯测试代码，通过 HTTP 调用其他服务的 API
- **测试数据集中管理**：测试用 PDF、截图、期望结果都在此服务中
- **测试结果持久化**：测试报告存入 MySQL（或文件），可追溯
- **支持 CI/CD**：提供 API 触发测试运行，返回结果

#### API 端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/v1/tests/run` | POST | 触发测试运行（指定 suite 或全部） |
| `/api/v1/tests/results` | GET | 查看历史测试结果 |
| `/api/v1/tests/results/{run_id}` | GET | 查看单次测试详情 |
| `/api/v1/tests/suites` | GET | 列出可用测试套件 |
| `/health` | GET | 健康检查 |

#### 测试套件

| Suite | 测试内容 | 调用的服务 |
|-------|---------|-----------|
| `indexing-unit` | Indexing API 功能测试（入库、检索、collection 管理） | Indexing |
| `agent-unit` | Agent API 功能测试（对话、VLM 分析） | Agent |
| `orchestrator-unit` | Orchestrator API 功能测试（上传、对话透传） | Orchestrator |
| `e2e-pipeline` | 端到端：上传 PDF → 入库 → 文本查询 → 验证回答 | Orchestrator → Indexing → Agent |
| `e2e-retrieval` | 检索质量评估：query → retrieve → 评分 | Indexing |

#### 测试数据管理

```
services/testing/
├── test_data/
│   ├── documents/           # 测试用 PDF/DOCX
│   │   ├── policy/          # 政策类文档
│   │   └── manual/          # 手册类文档
│   ├── queries/             # 测试查询集
│   │   └── eval_dataset.json  # {query, ground_truth, category}
│   └── expected/            # 期望结果（用于回归测试）
├── results/                 # 测试结果输出
│   └── {run_id}/
│       ├── report.json
│       └── details/
```

#### 依赖

```toml
[tool.poetry.dependencies]
python = "^3.10"
fastapi = ">=0.100"
uvicorn = ">=0.20"
httpx = ">=0.25"
httpx-sse = ">=0.4"
pytest = ">=7.0"
pandas = ">=2.0"           # 测试结果分析
```

---

## 3. 存储设计

### 3.1 MinIO（新增）

| Bucket | 用途 | 写入者 | 读取者 |
|--------|------|--------|--------|
| `raw-documents` | 原始上传文件 (PDF/DOCX) | Orchestrator | Indexing |
| `extracted-images` | 提取的截图 (JPEG/PNG) | Indexing | Agent (未来多模态) |

### 3.2 MySQL（保留 + 扩展）

```sql
-- 保留
CREATE TABLE IF NOT EXISTS parent_nodes (
    id VARCHAR(255) PRIMARY KEY,
    collection_name VARCHAR(255) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    text LONGTEXT NOT NULL,
    metadata JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_collection (collection_name),
    INDEX idx_file (file_name),
    INDEX idx_collection_file (collection_name, file_name)
);

-- 新增（替代 SQLite）
CREATE TABLE IF NOT EXISTS collections (
    name VARCHAR(255) PRIMARY KEY,
    config JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    collection_name VARCHAR(255) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    minio_key VARCHAR(500),
    file_size BIGINT DEFAULT 0,
    chunks_count INT DEFAULT 0,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_collection_file (collection_name, file_name),
    INDEX idx_collection (collection_name)
);

-- 新增：测试结果
CREATE TABLE IF NOT EXISTS test_runs (
    id VARCHAR(255) PRIMARY KEY,
    suite VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,       -- running | passed | failed
    summary JSON,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP NULL
);
```

### 3.3 Qdrant（保留）

- 向量配置不变：text (1536-dim) + sparse vectors
- Named Vectors 结构保留（为未来多模态 image vector 预留）

---

## 4. 目录结构

```
project-root/
├── services/
│   ├── orchestrator/                # 编排服务 (Port 8000)
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── app/
│   │       ├── main.py
│   │       ├── config.py            # ServiceSettings (下游 URL, MinIO)
│   │       ├── schemas.py           # 自定义请求/响应模型
│   │       ├── api/
│   │       │   └── routes.py
│   │       └── clients/
│   │           ├── indexing.py      # httpx → Indexing
│   │           ├── agent.py         # httpx-sse → Agent
│   │           └── minio.py         # MinIO 客户端
│   │
│   ├── indexing/                     # 数据层 (Port 8001)
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── app/
│   │       ├── main.py
│   │       ├── schemas.py           # 自定义请求/响应模型
│   │       ├── core/                # ← 原 shared/rag_shared/core/
│   │       │   ├── types.py         #   ABCs + ImageType
│   │       │   └── registry.py      #   ComponentRegistry
│   │       ├── config/              # ← 原 shared/rag_shared/config/
│   │       │   └── experiment.py    #   ExperimentConfig
│   │       ├── utils/               # ← 原 shared/rag_shared/utils/
│   │       │   ├── logger.py
│   │       │   └── role_mapper.py
│   │       ├── api/
│   │       │   └── routes.py        # index + retrieve + collections
│   │       ├── services/
│   │       │   ├── indexing.py      # 入库（解析→切片→向量化→存储）
│   │       │   └── retrieval.py     # 检索（Dense+Sparse+Rerank）
│   │       ├── storage/
│   │       │   ├── vectordb.py      # VectorStoreManager（读写合一）
│   │       │   ├── mysql_client.py
│   │       │   └── minio_client.py
│   │       ├── clients/
│   │       │   └── agent.py         # httpx → Agent VLM API
│   │       ├── components/
│   │       │   ├── chunkers/        # fixed, recursive, sentence, semantic
│   │       │   └── providers/       # dashscope, bgem3 (jieba)
│   │       └── parsing/
│   │           ├── parser.py        # pypdf + docx2txt
│   │           └── cleaner.py       # PolicyCleaner + ManualCleaner
│   │
│   ├── agent/                       # 推理层 (Port 8002)
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── app/
│   │       ├── main.py
│   │       ├── config.py
│   │       ├── schemas.py           # 自定义请求/响应模型
│   │       ├── utils/
│   │       │   └── logger.py
│   │       ├── api/
│   │       │   ├── routes.py        # /chat SSE
│   │       │   └── vlm_routes.py    # /vlm/analyze, /vlm/batch-analyze
│   │       ├── agent/
│   │       │   ├── workflow.py      # LangGraph 主图+子图
│   │       │   ├── state.py
│   │       │   ├── nodes.py
│   │       │   ├── tools.py         # knowledge_base_search → HTTP
│   │       │   └── prompts.py
│   │       ├── services/
│   │       │   └── vlm.py           # VLM 摘要/分析服务
│   │       └── clients/
│   │           └── indexing.py      # httpx → Indexing /retrieve
│   │
│   └── testing/                     # 测试层 (Port 8003)
│       ├── pyproject.toml
│       ├── Dockerfile
│       └── app/
│           ├── main.py
│           ├── config.py            # 所有服务的 URL 配置
│           ├── schemas.py
│           ├── api/
│           │   └── routes.py        # /tests/run, /tests/results
│           ├── suites/
│           │   ├── test_indexing.py  # Indexing 功能测试
│           │   ├── test_agent.py    # Agent 功能测试
│           │   ├── test_orchestrator.py  # Orchestrator 功能测试
│           │   └── test_e2e.py      # 端到端测试
│           ├── test_data/
│           │   ├── documents/       # 测试用 PDF
│           │   ├── queries/         # 测试查询集
│           │   └── expected/        # 期望结果
│           └── results/             # 测试输出
│
├── configs/                         # 配置文件（保留）
│   ├── default.yaml
│   ├── ablation_grid.yaml
│   └── ...
│
├── scripts/
│   ├── init_mysql.sql               # 更新：新增 collections + documents + test_runs 表
│   └── init_minio.sh                # 新增：创建 MinIO buckets
│
├── docker-compose.yml
└── .env.example
```

> 注：`shared/` 目录删除，`cli/` 目录删除（CLI 功能由 Testing Service 替代）。

---

## 5. docker-compose.yml

```yaml
version: "3.8"

services:
  # ── 基础设施 ──
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    networks:
      - rag_network

  mysql:
    image: mysql:8.0
    ports:
      - "3306:3306"
    environment:
      MYSQL_ROOT_PASSWORD: rag_password
      MYSQL_DATABASE: rag_db
      MYSQL_USER: rag_user
      MYSQL_PASSWORD: rag_password
    volumes:
      - mysql_data:/var/lib/mysql
      - ./scripts/init_mysql.sql:/docker-entrypoint-initdb.d/init.sql
    networks:
      - rag_network

  minio:
    image: minio/minio:latest
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    command: server /data --console-address ":9001"
    volumes:
      - minio_data:/data
    networks:
      - rag_network

  # ── 微服务 ──
  orchestrator:
    build:
      context: .
      dockerfile: services/orchestrator/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - INDEXING_URL=http://indexing:8001
      - AGENT_URL=http://agent:8002
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=minioadmin
      - MINIO_SECRET_KEY=minioadmin
      - DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY}
    depends_on:
      - minio
      - indexing
      - agent
    networks:
      - rag_network

  indexing:
    build:
      context: .
      dockerfile: services/indexing/Dockerfile
    ports:
      - "8001:8001"
    environment:
      - QDRANT_URL=http://qdrant:6333
      - MYSQL_URL=mysql+pymysql://rag_user:rag_password@mysql:3306/rag_db
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=minioadmin
      - MINIO_SECRET_KEY=minioadmin
      - AGENT_URL=http://agent:8002
      - DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY}
    depends_on:
      - qdrant
      - mysql
      - minio
    networks:
      - rag_network

  agent:
    build:
      context: .
      dockerfile: services/agent/Dockerfile
    ports:
      - "8002:8002"
    environment:
      - INDEXING_URL=http://indexing:8001
      - DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY}
    networks:
      - rag_network

  testing:
    build:
      context: .
      dockerfile: services/testing/Dockerfile
    ports:
      - "8003:8003"
    environment:
      - ORCHESTRATOR_URL=http://orchestrator:8000
      - INDEXING_URL=http://indexing:8001
      - AGENT_URL=http://agent:8002
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ACCESS_KEY=minioadmin
      - MINIO_SECRET_KEY=minioadmin
    depends_on:
      - orchestrator
    networks:
      - rag_network

volumes:
  qdrant_data:
  mysql_data:
  minio_data:

networks:
  rag_network:
    driver: bridge
```

---

## 6. 实施计划

### Phase 1：基础设施搭建

1. 更新 `docker-compose.yml`（新增 MinIO + Testing，重命名服务）
2. 更新 `scripts/init_mysql.sql`（新增 collections + documents + test_runs 表）
3. 创建 `scripts/init_minio.sh`（创建 raw-documents + extracted-images buckets）
4. 验证：`docker compose up -d` 所有基础设施容器正常

### Phase 2：Indexing Service

1. 创建 `services/indexing/` 目录结构
2. 迁入 shared 模块（types, registry, experiment, role_mapper）→ `app/core/`, `app/config/`, `app/utils/`
3. 迁入 ingestion 代码（chunkers, providers, parsing, storage）→ 逻辑不变
4. 迁入 inference 检索逻辑 → `app/services/retrieval.py`
5. 合并 VectorStoreManager（读写合一）
6. 新增 MinIO 客户端、MySQL 元数据管理（替代 SQLite）
7. 新增 Agent 客户端（入库时调用 VLM）
8. 实现 API 端点
9. 验证：curl 测试 /index 和 /retrieve

### Phase 3：Agent Service

1. 创建 `services/agent/` 目录结构
2. 迁入 LangGraph 工作流（workflow, state, nodes, prompts）
3. 迁入 VLM Provider → `app/services/vlm.py`
4. 重写 tools.py（knowledge_base_search → HTTP 调用 Indexing）
5. 新增 VLM API 端点（/vlm/analyze, /vlm/batch-analyze）
6. 实现 SSE 流式输出
7. 验证：curl 测试 /chat 和 /vlm/analyze

### Phase 4：Orchestrator Service

1. 创建 `services/orchestrator/` 目录结构
2. 实现 MinIO 客户端（文件上传）
3. 实现 Indexing 客户端 + Agent 客户端
4. 实现 API 端点（/upload, /chat, /collections）
5. 验证：curl 端到端测试

### Phase 5：Testing Service

1. 创建 `services/testing/` 目录结构
2. 迁移测试数据（从各服务 tests/datas/ 集中到 test_data/）
3. 实现测试套件（indexing-unit, agent-unit, e2e-pipeline）
4. 实现测试运行 API 和结果管理
5. 验证：触发测试运行，查看结果

### Phase 6：清理

1. 删除 `shared/` 目录
2. 删除 `services/ingestion/`, `services/inference/`, `services/gateway/`
3. 删除 `cli/` 目录
4. 更新 CLAUDE.md
5. 最终全栈验证

---

## 7. 验证方案

### 7.1 单服务测试

```bash
# Indexing
curl -X POST http://localhost:8001/api/v1/index \
  -H "Content-Type: application/json" \
  -d '{"minio_bucket":"raw-documents","minio_key":"test/manual.pdf","filename":"manual.pdf","config":{...}}'

curl -X POST http://localhost:8001/api/v1/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query":"如何提交毕业论文？","config":{...},"top_k":5}'

# Agent
curl -X POST http://localhost:8002/api/v1/vlm/analyze \
  -H "Content-Type: application/json" \
  -d '{"image_base64":"...","image_type":"screenshot","surrounding_text":"..."}'

curl -N -X POST http://localhost:8002/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"如何提交毕业论文？","config":{...}}'
```

### 7.2 端到端测试（Orchestrator）

```bash
curl -X POST http://localhost:8000/api/v1/upload \
  -F "file=@4-2 学生操作手册.pdf" \
  -F 'config={"chunking_strategy":"recursive","collection_name":"manual_test"}'

curl -N -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"导师一直没审核我的任务书怎么办？","config":{"collection_name":"manual_test"}}'
```

### 7.3 Testing Service 触发

```bash
curl -X POST http://localhost:8003/api/v1/tests/run \
  -H "Content-Type: application/json" \
  -d '{"suite": "e2e-pipeline"}'

curl http://localhost:8003/api/v1/tests/results
```

### 7.4 健康检查

```bash
curl http://localhost:8000/health   # Orchestrator
curl http://localhost:8001/health   # Indexing
curl http://localhost:8002/health   # Agent
curl http://localhost:8003/health   # Testing
curl http://localhost:6333/health   # Qdrant
curl http://localhost:9000/minio/health/live  # MinIO
```
